"""Tests for RefitDoseResponseCurve — point sort order, exclusion mapping,
and the Sprint-2 rich-payload + audit path."""

from __future__ import annotations

import uuid
from types import TracebackType
from typing import Self
from unittest.mock import AsyncMock

import pytest
from returns.result import Failure, Success

from cellar.application.screening.refit_dose_response import (
    ExclusionPayloadEntry,
    RefitDoseResponseCurve,
    RefitDoseResponseCurveCommand,
)
from cellar.domain.audit_compliance.enums import OperationType
from cellar.domain.screening_assay.curve_fitting import (
    DOSE_ZERO_LEFT_OUT,
    ConcentrationResponsePoint,
    FittedCurveResult,
    ResponseScale,
)
from cellar.domain.screening_assay.dose_response_config import DoseResponseConfig
from cellar.domain.screening_assay.dose_response_curve import DoseResponseCurve
from cellar.domain.screening_assay.enums import (
    CurveClass,
    CurveType,
    ProtocolType,
    ReadoutDataType,
    ReadoutNormalization,
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
        self.commit_called = False

    @property
    def is_active(self) -> bool:
        return False

    async def commit(self):
        self.commit_called = True
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

    def fit(self, points, config, scale=None):
        self.last_scale = scale
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
                raw_data=[
                    {"concentration": p.concentration, "response": p.response}
                    for p in points
                    if not p.is_excluded
                ],
                excluded_points=[
                    {"concentration": p.concentration, "response": p.response}
                    for p in points
                    if p.is_excluded
                ],
            )
        )


class _AuditSpy:
    """Captures the last ``record(...)`` invocation as kwargs."""

    def __init__(self) -> None:
        self.last_record: dict | None = None
        self.call_count = 0
        # When set, ``record`` raises this exception after capturing the call.
        # Used to prove audit failures roll back the surrounding transaction.
        self.fail_with: Exception | None = None

    async def record(self, **kwargs):
        self.call_count += 1
        self.last_record = kwargs
        if self.fail_with is not None:
            raise self.fail_with
        return object()  # AuditOperation stand-in


def _make_auth():
    auth = type("A", (), {})()
    auth.user_id = USER
    auth.workspace_id = WS

    def has_role(role):
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


def _make_protocol(layer: ReadoutNormalization | None = None) -> Protocol:
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
        readout_definitions=[
            ReadoutDefinition(
                protocol_id=rd.protocol_id,
                name="response",
                data_type=ReadoutDataType.NUMERIC,
                normalizations=frozenset({layer}) if layer else None,
            ),
            rd,
        ],
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


@pytest.mark.asyncio
async def test_a_refit_keeps_the_note_of_points_left_out_at_dose_zero():
    """The dose-0 points never reach the stored raw_data, so a refit cannot see them;
    the curve keeps saying they were left out."""
    curve = _make_curve_with_points([(1.0, 5.0), (10.0, 20.0), (100.0, 50.0), (1000.0, 80.0)])
    curve.fit_quality_warnings = ["low_r_squared", f"{DOSE_ZERO_LEFT_OUT}:2"]
    use_case, curve_repo = _make_use_case(curve)

    cmd = RefitDoseResponseCurveCommand(
        workspace_id=WS, curve_id=curve.id, excluded_point_indices=[]
    )
    assert isinstance(await use_case(cmd, auth=_make_auth()), Success)

    [saved] = curve_repo.save.await_args.args
    assert saved.fit_quality_warnings == [f"{DOSE_ZERO_LEFT_OUT}:2"]


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


@pytest.mark.asyncio
async def test_commit_refit_rich_payload_audit_failure_rolls_back():
    """Atomicity: when ``audit.record()`` raises, the surrounding UoW must NOT
    commit. ``session=self._uow.session`` is what binds the audit write to the
    same transaction as the curve save — this test locks that contract."""
    pairs = [(0.01, 5.0), (0.1, 10.0), (1.0, 20.0), (10.0, 60.0)]
    curve = _make_curve_with_points(pairs)
    audit = _AuditSpy()
    audit.fail_with = RuntimeError("audit went boom")
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
    )
    with pytest.raises(RuntimeError, match="audit went boom"):
        await use_case(cmd, auth=_make_auth())

    # The audit spy was reached (proving the path got that far)...
    assert audit.call_count == 1
    # ...but the UoW never committed: audit failure must abort the refit
    # atomically alongside the curve save.
    assert use_case._uow.commit_called is False


# ---------------------------------------------------------------------------
# One point order: suggestions, outlier-well entries and edits address the same set
# ---------------------------------------------------------------------------


def _left_out(points: list[ConcentrationResponsePoint]) -> list[tuple[float, float]]:
    return sorted((p.concentration, p.response) for p in points if p.is_excluded)


def _preview(curve, fitter):
    from cellar.application.screening.refit_dose_response_preview import (
        RefitDoseResponseCurvePreview,
    )

    curve_repo = AsyncMock()
    curve_repo.find_by_id_in_workspace = AsyncMock(return_value=curve)
    protocol_repo = AsyncMock()
    protocol_repo.find_by_id_in_workspace = AsyncMock(return_value=_make_protocol())
    return RefitDoseResponseCurvePreview(
        uow=_FakeUow(), curve_repo=curve_repo, protocol_repo=protocol_repo, curve_fitter=fitter
    )


def _auto_fitted_curve() -> DoseResponseCurve:
    """The auto-fit's curve: the 0.1 µM well is flagged as an outlier (left out), and the
    fitter suggests the 1 µM point — raw_data index 1, captured-set position 2."""
    from cellar.application.screening.fit_dose_response import _build_excluded_from_fitter
    from cellar.domain.screening_assay.outlier_suggestion import OutlierSuggestion

    raw = [(0.01, 2.0), (1.0, 80.0), (10.0, 90.0), (100.0, 98.0), (1000.0, 99.0)]
    fitted = FittedCurveResult(
        fitted_value=1.0, hill_slope=1.0, top=100.0, bottom=0.0, r_squared=0.9,
        confidence_interval_low=None, confidence_interval_high=None,
        curve_class=CurveClass.FULL, num_points=len(raw),
        raw_data=[{"concentration": c, "response": r} for c, r in raw],
        excluded_points=[{"concentration": 0.1, "response": -40.0}],
        outlier_suggestions=(
            OutlierSuggestion(idx=1, concentration=1.0, response=80.0, residual_z_full_sd=4.0),
        ),
    )  # fmt: skip
    curve = _make_curve_with_points(raw)
    curve.excluded_points = _build_excluded_from_fitter(fitted)
    return curve


def _every_entry_addresses_its_point(curve: DoseResponseCurve) -> None:
    from cellar.application.screening._dr_point_reconstruction import captured_set

    captured = captured_set(curve.raw_data, curve.excluded_points)
    for e in curve.excluded_points:
        assert captured[e.idx][:2] == (e.concentration, e.response), e


@pytest.mark.asyncio
async def test_accepting_a_suggestion_above_an_outlier_well_leaves_out_that_point_only():
    """The editor sends every entry back with its idx, the suggestion accepted: the preview
    and the save both leave out the 1 µM point (and the flagged 0.1 µM one), nothing else."""
    curve = _auto_fitted_curve()
    _every_entry_addresses_its_point(curve)
    accepted = [
        ExclusionPayloadEntry(idx=e.idx, source=e.source, excluded=True, reason=e.reason)
        for e in curve.excluded_points
    ]
    preview_fitter = _RecordingFitter()
    preview = _preview(curve, preview_fitter)
    from cellar.application.screening.refit_dose_response_preview import PreviewRefitCommand

    previewed = await preview(
        PreviewRefitCommand(
            workspace_id=WS, curve_id=curve.id,
            excluded_point_indices=[e.idx for e in accepted],
        ),
        auth=_make_auth(),
    )  # fmt: skip
    fitter = _RecordingFitter()
    use_case, curve_repo = _make_use_case(curve, fitter=fitter)
    saved = await use_case(
        RefitDoseResponseCurveCommand(
            workspace_id=WS, curve_id=curve.id, exclusions=accepted,
            save_reason=ExclusionReason.OUTLIER,
        ),
        auth=_make_auth(),
    )  # fmt: skip

    assert isinstance(previewed, Success) and isinstance(saved, Success)
    expected = [(0.1, -40.0), (1.0, 80.0)]
    assert _left_out(preview_fitter.last_points) == expected
    assert _left_out(fitter.last_points) == expected
    [curve_saved] = curve_repo.save.await_args.args
    _every_entry_addresses_its_point(curve_saved)


@pytest.mark.asyncio
async def test_a_save_keeps_every_entry_on_its_point_when_replicates_change_places():
    """Two 1 µM replicates; excluding the first moves it behind the second in the stored
    captured set (raw_data first). The saved entry follows its point."""
    curve = _make_curve_with_points(
        [(0.01, 2.0), (1.0, 30.0), (1.0, 70.0), (10.0, 90.0), (100.0, 98.0)]
    )
    use_case, curve_repo = _make_use_case(curve)

    await use_case(
        RefitDoseResponseCurveCommand(
            workspace_id=WS, curve_id=curve.id, save_reason=ExclusionReason.OUTLIER,
            exclusions=[ExclusionPayloadEntry(
                idx=1, source=ExclusionSource.MANUAL, excluded=True,
                reason=ExclusionReason.OUTLIER,
            )],
        ),
        auth=_make_auth(),
    )  # fmt: skip

    [saved] = curve_repo.save.await_args.args
    [entry] = saved.excluded_points
    assert (entry.concentration, entry.response) == (1.0, 30.0)
    _every_entry_addresses_its_point(saved)


# ---------------------------------------------------------------------------
# A point of an outlier well cannot be re-included from the curve editor
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_an_outlier_well_point_stays_out_when_the_editor_includes_it():
    """The editor sends the flagged point's entry back as included (and the preview leaves
    it out of its indices): preview and save still leave it out, and the curve keeps the
    flag's entry."""
    curve = _auto_fitted_curve()
    flag = next(e for e in curve.excluded_points if e.source == ExclusionSource.WELL_FLAG)
    preview_fitter = _RecordingFitter()
    from cellar.application.screening.refit_dose_response_preview import PreviewRefitCommand

    await _preview(curve, preview_fitter)(
        PreviewRefitCommand(workspace_id=WS, curve_id=curve.id, excluded_point_indices=[]),
        auth=_make_auth(),
    )
    fitter = _RecordingFitter()
    use_case, curve_repo = _make_use_case(curve, fitter=fitter)
    await use_case(
        RefitDoseResponseCurveCommand(
            workspace_id=WS, curve_id=curve.id, save_reason=ExclusionReason.OTHER,
            exclusions=[
                ExclusionPayloadEntry(
                    idx=flag.idx, source=ExclusionSource.WELL_FLAG, excluded=False,
                    reason=ExclusionReason.OUTLIER_WELL,
                ),
                ExclusionPayloadEntry(
                    idx=flag.idx, source=ExclusionSource.MANUAL, excluded=False,
                    reason=ExclusionReason.OTHER,
                ),
            ],
        ),
        auth=_make_auth(),
    )  # fmt: skip

    assert _left_out(preview_fitter.last_points) == [(0.1, -40.0)]
    assert _left_out(fitter.last_points) == [(0.1, -40.0)]
    [saved] = curve_repo.save.await_args.args
    [kept] = [e for e in saved.excluded_points if e.excluded]
    assert (kept.source, kept.concentration, kept.excluded) == (
        ExclusionSource.WELL_FLAG, 0.1, True,
    )  # fmt: skip
    _every_entry_addresses_its_point(saved)


@pytest.mark.asyncio
async def test_a_constraint_refit_keeps_an_outlier_well_point_out_and_recorded():
    """The constraint-edit (legacy) path sends no indices: the flagged point stays out of
    the fit and its typed entry stays on the curve."""
    curve = _auto_fitted_curve()
    fitter = _RecordingFitter()
    use_case, curve_repo = _make_use_case(curve, fitter=fitter)

    await use_case(
        RefitDoseResponseCurveCommand(
            workspace_id=WS, curve_id=curve.id, excluded_point_indices=[]
        ),
        auth=_make_auth(),
    )

    assert _left_out(fitter.last_points) == [(0.1, -40.0)]
    [saved] = curve_repo.save.await_args.args
    [kept] = saved.excluded_points
    assert (kept.source, kept.idx, kept.concentration) == (ExclusionSource.WELL_FLAG, 1, 0.1)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("layer", "scale"),
    [(ReadoutNormalization.PERCENT_INHIBITION, ResponseScale()), (None, None)],
)
async def test_the_curve_is_refitted_on_its_layers_response_scale(layer, scale):
    """The curve's own readout reads a % inhibition layer: refitted on 0-100 %; a raw one
    on no scale."""
    protocol = _make_protocol(layer)
    dr_def = next(rd for rd in protocol.readout_definitions if rd.name == "IC50")
    curve = _make_curve_with_points([(1.0, 5.0), (10.0, 20.0), (100.0, 50.0), (1000.0, 80.0)])
    curve.readout_definition_id = dr_def.id
    fitter = _RecordingFitter()
    use_case, _ = _make_use_case(curve, fitter=fitter)
    use_case._protocol_repo.find_by_id_in_workspace = AsyncMock(return_value=protocol)
    cmd = RefitDoseResponseCurveCommand(workspace_id=WS, curve_id=curve.id)

    result = await use_case(cmd, auth=_make_auth())

    assert isinstance(result, Success)
    assert fitter.last_scale == scale
