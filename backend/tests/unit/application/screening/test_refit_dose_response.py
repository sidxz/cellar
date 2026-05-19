"""Tests for RefitDoseResponseCurve — point sort order, exclusion mapping,
and the Sprint-2 rich-payload + audit path."""

from __future__ import annotations

import uuid
from types import TracebackType
from typing import Self
from unittest.mock import AsyncMock, MagicMock

import pytest
from returns.result import Failure, Success

from cellar.application.screening.refit_dose_response import (
    ExclusionPayloadEntry,
    RefitDoseResponseCurve,
    RefitDoseResponseCurveCommand,
)
from cellar.domain.audit_compliance.enums import OperationType
from cellar.domain.screening_assay.curve_fitting import (
    ConcentrationResponsePoint,
    FittedCurveResult,
)
from cellar.domain.screening_assay.dose_response_config import DoseResponseConfig
from cellar.domain.screening_assay.dose_response_curve import DoseResponseCurve
from cellar.domain.screening_assay.enums import (
    CurveClass,
    CurveType,
    ProtocolType,
    ReadoutDataType,
)
from cellar.domain.screening_assay.excluded_point_detail import (
    ExclusionReason,
    ExclusionSource,
)
from cellar.domain.screening_assay.protocol import Protocol, ReadoutDefinition


WS = uuid.uuid4()
USER = uuid.uuid4()


class _FakeUow:
    """Minimal UoW double — exposes ``session`` so audit calls can thread it."""

    def __init__(self) -> None:
        # Any sentinel — the audit spy just records the kwarg.
        self.session = object()

    @property
    def is_active(self) -> bool:
        return False

    async def commit(self):
        return []

    async def rollback(self) -> None:
        pass

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        pass


class _RecordingFitter:
    def __init__(self) -> None:
        self.last_points: list[ConcentrationResponsePoint] = []
        self.last_config: DoseResponseConfig | None = None

    def fit(self, points, config):
        self.last_points = list(points)
        self.last_config = config
        return Success(
            FittedCurveResult(
                fitted_value=1.0,
                hill_slope=1.0,
                top=100.0,
                bottom=0.0,
                r_squared=0.99,
                confidence_interval_low=0.5,
                confidence_interval_high=2.0,
                curve_class=CurveClass.FULL,
                num_points=len(points),
                raw_data=[],
                excluded_points=[],
            )
        )


class _AuditSpy:
    """Captures the last ``record(...)`` invocation as kwargs."""

    def __init__(self) -> None:
        self.last_record: dict | None = None
        self.call_count = 0

    async def record(self, **kwargs):
        self.call_count += 1
        self.last_record = kwargs
        return object()  # AuditOperation stand-in


def _make_auth():
    auth = type("A", (), {})()
    auth.user_id = USER
    auth.workspace_id = WS

    def has_role(role):  # noqa: ANN001
        return True

    auth.has_role = has_role
    return auth


def _make_curve_with_points(points: list[tuple[float, float]]) -> DoseResponseCurve:
    """Build a curve whose raw_data carries the given (concentration, response) pairs."""
    return DoseResponseCurve(
        id=uuid.uuid4(),
        workspace_id=WS,
        molecule_id=uuid.uuid4(),
        batch_id=uuid.uuid4(),
        protocol_id=uuid.uuid4(),
        run_id=uuid.uuid4(),
        readout_definition_id=uuid.uuid4(),
        curve_type=CurveType.IC50,
        fitted_value=10.0,
        hill_slope=1.0,
        top=100.0,
        bottom=0.0,
        r_squared=0.95,
        num_points=len(points),
        raw_data=[{"concentration": c, "response": r} for c, r in points],
        excluded_points=[],
    )


def _make_protocol() -> Protocol:
    rd = ReadoutDefinition(
        protocol_id=uuid.uuid4(),
        name="IC50",
        data_type=ReadoutDataType.DOSE_RESPONSE,
        dose_response_config=DoseResponseConfig(
            curve_type=CurveType.IC50,
            x_readout_name="concentration",
            y_readout_name="response",
        ),
    )
    return Protocol.create(
        workspace_id=WS,
        name="Test",
        protocol_type=ProtocolType.BIOCHEMICAL,
        created_by=USER,
        readout_definitions=[rd],
    )


def _make_use_case(curve, *, audit=None, fitter=None):
    curve_repo = AsyncMock()
    curve_repo.find_by_id_in_workspace = AsyncMock(return_value=curve)
    curve_repo.save = AsyncMock()
    protocol_repo = AsyncMock()
    protocol_repo.find_by_id_in_workspace = AsyncMock(return_value=_make_protocol())
    guard = AsyncMock()
    guard.guard_write = AsyncMock()

    return (
        RefitDoseResponseCurve(
            uow=_FakeUow(),
            curve_repo=curve_repo,
            protocol_repo=protocol_repo,
            curve_fitter=fitter or _RecordingFitter(),
            guard=guard,
            audit=audit or _AuditSpy(),
        ),
        curve_repo,
    )


@pytest.mark.asyncio
async def test_excluded_index_maps_to_ascending_dose_order():
    """F1: when the user passes excluded_point_indices=[1] and there are 5
    points 1.0, 10.0, 100.0, 1000.0, 10000.0, the excluded point must be the
    second smallest dose (10.0), matching the UI's ascending display order."""
    pairs = [(1.0, 5.0), (10.0, 20.0), (100.0, 50.0), (1000.0, 80.0), (10000.0, 95.0)]
    # Insert in arbitrary order — the use case is responsible for sorting.
    shuffled_pairs = [pairs[2], pairs[0], pairs[4], pairs[1], pairs[3]]
    curve = _make_curve_with_points(shuffled_pairs)
    fitter = _RecordingFitter()
    use_case, _ = _make_use_case(curve, fitter=fitter)

    cmd = RefitDoseResponseCurveCommand(
        workspace_id=WS,
        curve_id=curve.id,
        excluded_point_indices=[1],
    )
    result = await use_case(cmd, auth=_make_auth())
    assert isinstance(result, Success)

    excluded = [p for p in fitter.last_points if p.is_excluded]
    assert len(excluded) == 1
    # Ascending order: index 1 = 10.0 µM, response 20.0
    assert excluded[0].concentration == pytest.approx(10.0)
    assert excluded[0].response == pytest.approx(20.0)

    # Sanity: kept points span the rest in ascending dose order.
    kept = [p for p in fitter.last_points if not p.is_excluded]
    kept_concs = [p.concentration for p in kept]
    assert kept_concs == sorted(kept_concs)
    # And the excluded point is NOT among the kept (descending-sort regression).
    assert 10.0 not in kept_concs

    # Final guard: with descending sort (the bug), index 1 would land on 1000.0.
    # Make sure that's not what happened.
    assert excluded[0].concentration != pytest.approx(1000.0)


@pytest.mark.asyncio
async def test_refit_with_disable_auto_outliers_passes_none_sigma_to_fitter():
    """When the user is editing points by hand, ``disable_auto_outliers=True``
    must force ``outlier_sigma=None`` in the fit config so the fitter does not
    cascade additional 3σ exclusions on top of the user's choice."""
    pairs = [(1.0, 5.0), (10.0, 20.0), (100.0, 50.0)]
    curve = _make_curve_with_points(pairs)
    fitter = _RecordingFitter()
    use_case, _ = _make_use_case(curve, fitter=fitter)

    cmd = RefitDoseResponseCurveCommand(
        workspace_id=WS,
        curve_id=curve.id,
        excluded_point_indices=[0],
        disable_auto_outliers=True,
    )
    result = await use_case(cmd, auth=_make_auth())
    assert isinstance(result, Success)
    assert fitter.last_config is not None
    assert fitter.last_config.outlier_sigma is None


@pytest.mark.asyncio
async def test_refit_without_disable_auto_outliers_preserves_protocol_sigma():
    """Sanity: default behavior (flag False) must NOT clobber the protocol's
    configured ``outlier_sigma`` — the fitter still does its auto-3σ pass."""
    pairs = [(1.0, 5.0), (10.0, 20.0), (100.0, 50.0)]
    curve = _make_curve_with_points(pairs)
    fitter = _RecordingFitter()
    use_case, _ = _make_use_case(curve, fitter=fitter)

    cmd = RefitDoseResponseCurveCommand(
        workspace_id=WS,
        curve_id=curve.id,
        excluded_point_indices=[],
    )
    result = await use_case(cmd, auth=_make_auth())
    assert isinstance(result, Success)
    assert fitter.last_config is not None
    # Protocol default sigma is whatever ``DoseResponseConfig`` ships as the
    # default (currently 3.0 via ``DEFAULT_OUTLIER_SIGMA``); the key assertion
    # is that the use case did not silently swap it to None.
    assert fitter.last_config.outlier_sigma is not None


# ---------------------------------------------------------------------------
# Sprint-2: rich exclusions payload + audit operation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_commit_refit_with_rich_payload_persists_excluded_point_detail():
    """Sprint 2 commit: rich exclusions[] becomes ExcludedPointDetail in the saved curve."""
    pairs = [(0.01, 5.0), (0.1, 10.0), (1.0, 20.0), (10.0, 60.0), (100.0, 95.0), (1000.0, 99.0)]
    curve = _make_curve_with_points(pairs)
    use_case, curve_repo = _make_use_case(curve)

    cmd = RefitDoseResponseCurveCommand(
        workspace_id=WS,
        curve_id=curve.id,
        exclusions=[
            ExclusionPayloadEntry(
                idx=2,
                source=ExclusionSource.MANUAL,
                excluded=True,
                reason=ExclusionReason.OUTLIER,
                note="dispense spike",
            ),
            ExclusionPayloadEntry(
                idx=5,
                source=ExclusionSource.AUTO_3SIGMA,
                excluded=False,
                reason=ExclusionReason.AUTO_3SIGMA,
            ),
        ],
        save_reason=ExclusionReason.OUTLIER,
        save_note="lid dropped on plate",
    )
    result = await use_case(cmd, auth=_make_auth())
    assert isinstance(result, Success), getattr(result, "_inner_value", result)

    saved_curve = curve_repo.save.call_args.args[0]
    assert saved_curve.excluded_points is not None

    # Manual exclusion present with author + reason + note + ts
    manual = next(e for e in saved_curve.excluded_points if e.idx == 2)
    assert manual.source == ExclusionSource.MANUAL
    assert manual.excluded is True
    assert manual.author_id == USER
    assert manual.note == "dispense spike"
    assert manual.reason == ExclusionReason.OUTLIER

    # Suggestion preserved as is_suggestion (AUTO_3SIGMA + excluded=False)
    suggestion = next(e for e in saved_curve.excluded_points if e.idx == 5)
    assert suggestion.source == ExclusionSource.AUTO_3SIGMA
    assert suggestion.excluded is False
    assert suggestion.is_suggestion is True
    # AUTO source must NOT carry an author_id (the fitter wrote it, not a user).
    assert suggestion.author_id is None


@pytest.mark.asyncio
async def test_commit_refit_with_rich_payload_creates_audit_operation():
    """Sprint-2 commit must record an AuditOperation of type CURVE_POINT_EXCLUSION."""
    pairs = [(0.01, 5.0), (0.1, 10.0), (1.0, 20.0), (10.0, 60.0), (100.0, 95.0), (1000.0, 99.0)]
    curve = _make_curve_with_points(pairs)
    audit = _AuditSpy()
    use_case, _ = _make_use_case(curve, audit=audit)

    cmd = RefitDoseResponseCurveCommand(
        workspace_id=WS,
        curve_id=curve.id,
        exclusions=[
            ExclusionPayloadEntry(
                idx=2,
                source=ExclusionSource.MANUAL,
                excluded=True,
                reason=ExclusionReason.OUTLIER,
            ),
        ],
        save_reason=ExclusionReason.OUTLIER,
        save_note="lid dropped on plate",
    )
    result = await use_case(cmd, auth=_make_auth())
    assert isinstance(result, Success)

    assert audit.call_count == 1
    rec = audit.last_record
    assert rec is not None
    assert rec["operation_type"] == OperationType.CURVE_POINT_EXCLUSION
    assert rec["entity_type"] == "DoseResponseCurve"
    assert rec["entity_id"] == curve.id
    assert rec["user_id"] == USER
    assert rec["workspace_id"] == WS
    # Reason carries save_reason + save_note for the audit trail.
    assert "outlier" in (rec["reason"] or "").lower()
    assert "lid dropped on plate" in (rec["reason"] or "")
    # Exactly one entry: the excluded_points field-level diff.
    entries = rec["entries"]
    assert len(entries) == 1
    assert entries[0].field_name == "excluded_points"
    assert entries[0].old_value is not None
    assert entries[0].new_value is not None


@pytest.mark.asyncio
async def test_commit_refit_with_rich_payload_forces_outlier_sigma_none():
    """Sprint-2 path: outlier_sigma is unconditionally None even if the
    protocol has one configured AND ``disable_auto_outliers`` is left False."""
    pairs = [(0.01, 5.0), (0.1, 10.0), (1.0, 20.0), (10.0, 60.0)]
    curve = _make_curve_with_points(pairs)
    fitter = _RecordingFitter()
    use_case, _ = _make_use_case(curve, fitter=fitter)

    cmd = RefitDoseResponseCurveCommand(
        workspace_id=WS,
        curve_id=curve.id,
        exclusions=[
            ExclusionPayloadEntry(
                idx=2,
                source=ExclusionSource.MANUAL,
                excluded=True,
                reason=ExclusionReason.OUTLIER,
            ),
        ],
        save_reason=ExclusionReason.OUTLIER,
        # Note: disable_auto_outliers explicitly left as default False — the
        # Sprint-2 path must force outlier_sigma=None anyway.
    )
    result = await use_case(cmd, auth=_make_auth())
    assert isinstance(result, Success)
    assert fitter.last_config is not None
    assert fitter.last_config.outlier_sigma is None


@pytest.mark.asyncio
async def test_commit_refit_sprint_1_path_does_not_create_audit_operation():
    """Sprint 1 callers (excluded_point_indices only) keep their pre-Sprint-2
    contract: no AuditOperation is recorded."""
    pairs = [(0.01, 5.0), (0.1, 10.0), (1.0, 20.0)]
    curve = _make_curve_with_points(pairs)
    audit = _AuditSpy()
    use_case, _ = _make_use_case(curve, audit=audit)

    cmd = RefitDoseResponseCurveCommand(
        workspace_id=WS,
        curve_id=curve.id,
        excluded_point_indices=[2],
    )
    result = await use_case(cmd, auth=_make_auth())
    assert isinstance(result, Success)
    assert audit.call_count == 0
    assert audit.last_record is None


@pytest.mark.asyncio
async def test_commit_refit_rich_payload_requires_auth():
    """Sprint-2 path with auth=None must Failure — the AuditOperation has
    no defensible author otherwise."""
    pairs = [(0.01, 5.0), (0.1, 10.0), (1.0, 20.0)]
    curve = _make_curve_with_points(pairs)
    use_case, _ = _make_use_case(curve)

    cmd = RefitDoseResponseCurveCommand(
        workspace_id=WS,
        curve_id=curve.id,
        exclusions=[
            ExclusionPayloadEntry(
                idx=2,
                source=ExclusionSource.MANUAL,
                excluded=True,
                reason=ExclusionReason.OUTLIER,
            ),
        ],
        save_reason=ExclusionReason.OUTLIER,
    )
    result = await use_case(cmd, auth=None)
    assert isinstance(result, Failure)
