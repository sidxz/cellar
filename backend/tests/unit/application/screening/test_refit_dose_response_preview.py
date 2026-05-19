"""Tests for RefitDoseResponseCurvePreview — compute-only, no persist, no auto-outlier."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

import pytest
from returns.result import Failure, Success

from cellar.application.screening.refit_dose_response_preview import (
    PreviewRefitCommand,
    RefitDoseResponseCurvePreview,
)
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
from cellar.domain.screening_assay.protocol import Protocol, ReadoutDefinition


WS = uuid.uuid4()
USER = uuid.uuid4()


class _RecordingFitter:
    """Spy fitter — captures last invocation and returns a canned Success."""

    def __init__(self) -> None:
        self.last_points: list[ConcentrationResponsePoint] = []
        self.last_config: DoseResponseConfig | None = None
        self.call_count: int = 0

    def fit(self, points, config):
        self.call_count += 1
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


def _make_auth():
    auth = type("A", (), {})()
    auth.user_id = USER
    auth.workspace_id = WS

    def has_role(role):  # noqa: ANN001
        return True

    auth.has_role = has_role
    return auth


def _make_curve_with_points(points: list[tuple[float, float]]) -> DoseResponseCurve:
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


def _build_use_case(curve, fitter):
    """Wire a use case with a curve_repo that returns ``curve`` (or None) and a
    save spy we can assert is never called."""
    curve_repo = AsyncMock()
    curve_repo.find_by_id_in_workspace = AsyncMock(return_value=curve)
    curve_repo.save = AsyncMock()
    protocol_repo = AsyncMock()
    protocol_repo.find_by_id_in_workspace = AsyncMock(return_value=_make_protocol())
    return (
        RefitDoseResponseCurvePreview(
            curve_repo=curve_repo,
            protocol_repo=protocol_repo,
            curve_fitter=fitter,
        ),
        curve_repo,
    )


@pytest.mark.asyncio
async def test_preview_returns_fit_without_persisting():
    """CRITICAL: preview MUST NOT write to the repository."""
    pairs = [(1.0, 5.0), (10.0, 20.0), (100.0, 50.0), (1000.0, 80.0)]
    curve = _make_curve_with_points(pairs)
    fitter = _RecordingFitter()
    use_case, curve_repo = _build_use_case(curve, fitter)

    cmd = PreviewRefitCommand(
        workspace_id=WS,
        curve_id=curve.id,
        excluded_point_indices=[2],
    )
    result = await use_case(cmd, auth=_make_auth())

    assert isinstance(result, Success)
    preview = result.unwrap()
    assert preview.fitted_value == pytest.approx(1.0)
    assert preview.r_squared == pytest.approx(0.99)
    assert preview.points_in_fit == 3
    assert preview.points_total == 4
    # CRITICAL: no persist
    curve_repo.save.assert_not_called()


@pytest.mark.asyncio
async def test_preview_unconditionally_disables_auto_outlier_sigma():
    """CRITICAL: outlier_sigma is None EVEN WHEN the caller did not request
    disable_auto_outliers. Preview always cedes outlier control to the chemist."""
    pairs = [(1.0, 5.0), (10.0, 20.0), (100.0, 50.0)]
    curve = _make_curve_with_points(pairs)
    fitter = _RecordingFitter()
    use_case, _ = _build_use_case(curve, fitter)

    cmd = PreviewRefitCommand(
        workspace_id=WS,
        curve_id=curve.id,
        excluded_point_indices=[],
    )
    result = await use_case(cmd, auth=_make_auth())

    assert isinstance(result, Success)
    assert fitter.last_config is not None
    # CRITICAL: auto-outlier never runs during preview
    assert fitter.last_config.outlier_sigma is None


@pytest.mark.asyncio
async def test_preview_returns_failure_for_missing_curve():
    fitter = _RecordingFitter()
    use_case, _ = _build_use_case(None, fitter)

    cmd = PreviewRefitCommand(
        workspace_id=WS,
        curve_id=uuid.uuid4(),
        excluded_point_indices=[],
    )
    result = await use_case(cmd, auth=_make_auth())

    assert isinstance(result, Failure)
    # Fitter should never have been called for a missing curve.
    assert fitter.call_count == 0


@pytest.mark.asyncio
async def test_preview_excluded_index_maps_to_ascending_dose_order():
    """Mirror of the commit-path test: index→dose mapping must be ascending
    so the FE's draft set lines up with the same fit Save would produce."""
    pairs = [(1.0, 5.0), (10.0, 20.0), (100.0, 50.0), (1000.0, 80.0), (10000.0, 95.0)]
    shuffled = [pairs[2], pairs[0], pairs[4], pairs[1], pairs[3]]
    curve = _make_curve_with_points(shuffled)
    fitter = _RecordingFitter()
    use_case, _ = _build_use_case(curve, fitter)

    cmd = PreviewRefitCommand(
        workspace_id=WS,
        curve_id=curve.id,
        excluded_point_indices=[1],
    )
    result = await use_case(cmd, auth=_make_auth())

    assert isinstance(result, Success)
    excluded = [p for p in fitter.last_points if p.is_excluded]
    assert len(excluded) == 1
    assert excluded[0].concentration == pytest.approx(10.0)
    assert excluded[0].response == pytest.approx(20.0)
