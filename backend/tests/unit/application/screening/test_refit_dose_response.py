"""Tests for RefitDoseResponseCurve — point sort order and exclusion mapping."""

from __future__ import annotations

import uuid
from types import TracebackType
from typing import Self
from unittest.mock import AsyncMock

import pytest
from returns.result import Success

from cellar.application.screening.refit_dose_response import (
    RefitDoseResponseCurve,
    RefitDoseResponseCurveCommand,
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


class _FakeUow:
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

    def fit(self, points, config):
        self.last_points = list(points)
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


@pytest.mark.asyncio
async def test_excluded_index_maps_to_ascending_dose_order():
    """F1: when the user passes excluded_point_indices=[1] and there are 5
    points 1.0, 10.0, 100.0, 1000.0, 10000.0, the excluded point must be the
    second smallest dose (10.0), matching the UI's ascending display order."""
    pairs = [(1.0, 5.0), (10.0, 20.0), (100.0, 50.0), (1000.0, 80.0), (10000.0, 95.0)]
    # Insert in arbitrary order — the use case is responsible for sorting.
    shuffled_pairs = [pairs[2], pairs[0], pairs[4], pairs[1], pairs[3]]
    curve = _make_curve_with_points(shuffled_pairs)

    curve_repo = AsyncMock()
    curve_repo.find_by_id_in_workspace = AsyncMock(return_value=curve)
    curve_repo.save = AsyncMock()
    protocol_repo = AsyncMock()
    protocol_repo.find_by_id_in_workspace = AsyncMock(return_value=_make_protocol())
    fitter = _RecordingFitter()

    guard = AsyncMock()
    guard.guard_write = AsyncMock()
    use_case = RefitDoseResponseCurve(
        uow=_FakeUow(),
        curve_repo=curve_repo,
        protocol_repo=protocol_repo,
        curve_fitter=fitter,
        guard=guard,
    )

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
