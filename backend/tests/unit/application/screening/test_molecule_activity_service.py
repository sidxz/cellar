"""Tests for MoleculeActivityService.enrich_molecules — ActivityValue enrichment.

Most of the file mocks the persistence ports (curve_repo, run_repo) and
exercises the application-layer aggregation pipeline. The integration
between the aggregator + the SQL repos is covered by
``tests/integration/test_dose_response_curve_repository_find_all.py``
(Task 5) and ``tests/integration/test_run_repository_find_by_ids.py``.
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import Self
from unittest.mock import AsyncMock

import pytest

from cellar.application.screening.molecule_activity_service import (
    MoleculeActivityService,
)
from cellar.domain.screening_assay.aggregation_types import SelectionRule
from cellar.domain.screening_assay.curve_fitting import InterceptValue
from cellar.domain.screening_assay.dose_response_config import (
    InterceptBasis,
    InterceptKind,
    InterceptSpec,
)
from cellar.domain.screening_assay.dose_response_curve import DoseResponseCurve
from cellar.domain.screening_assay.enums import CurveClass, CurveType, RunStatus
from cellar.domain.screening_assay.run import Run
from cellar.domain.screening_assay.run_scope import RunScope

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

WS = uuid.uuid4()
MOL_ID = uuid.uuid4()
PROTO_ID = uuid.uuid4()
RD_ID = uuid.uuid4()


class _FakeUoW:
    is_active = True

    async def commit(self) -> list:
        return []

    async def rollback(self) -> None:
        pass

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *args: object) -> None:
        pass


def _make_curve(
    *,
    molecule_id: uuid.UUID = MOL_ID,
    protocol_id: uuid.UUID = PROTO_ID,
    readout_definition_id: uuid.UUID = RD_ID,
    curve_type: CurveType = CurveType.IC50,
    fitted_value: float = 5.2,
    hill_slope: float = -1.1,
    top: float = 100.0,
    bottom: float = 0.5,
    r_squared: float = 0.97,
    num_points: int = 8,
    curve_class: CurveClass | None = CurveClass.FULL,
    raw_data: list[dict] | None = None,
    confidence_interval_low: float | None = 3.8,
    confidence_interval_high: float | None = 7.1,
    intercept_values: list[InterceptValue] | None = None,
    run_id: uuid.UUID | None = None,
) -> DoseResponseCurve:
    return DoseResponseCurve(
        workspace_id=WS,
        molecule_id=molecule_id,
        batch_id=uuid.uuid4(),
        protocol_id=protocol_id,
        run_id=run_id or uuid.uuid4(),
        readout_definition_id=readout_definition_id,
        curve_type=curve_type,
        fitted_value=fitted_value,
        hill_slope=hill_slope,
        top=top,
        bottom=bottom,
        r_squared=r_squared,
        num_points=num_points,
        curve_class=curve_class,
        raw_data=raw_data,
        confidence_interval_low=confidence_interval_low,
        confidence_interval_high=confidence_interval_high,
        intercept_values=intercept_values,
    )


def _make_run(
    *,
    run_id: uuid.UUID,
    run_date: date,
    status: RunStatus = RunStatus.APPROVED,
    protocol_id: uuid.UUID = PROTO_ID,
) -> Run:
    """Build a Run aggregate suitable as a `find_by_ids` payload row.

    Defaults to APPROVED so the aggregator's LATEST_APPROVED_RUN treats
    every seeded run as approved (matches the "all runs approved" common
    case in test scenarios). Override per-test when exercising mixed-status
    behavior.
    """
    return Run(
        id=run_id,
        workspace_id=WS,
        protocol_id=protocol_id,
        run_date=run_date,
        operator=uuid.uuid4(),
        status=status,
    )


def _make_intercept_value(
    *, kind: InterceptKind, level: float, label: str, value: float, at_bound: bool = False
) -> InterceptValue:
    return InterceptValue(
        spec=InterceptSpec(
            kind=kind,
            level=level,
            basis=InterceptBasis.RELATIVE_PERCENT,
            label=label,
        ),
        value=value,
        confidence_interval_low=None,
        confidence_interval_high=None,
        at_bound=at_bound,
    )


def _seed_runs(
    dates_and_values: list[tuple[date, float]],
    *,
    status: RunStatus = RunStatus.APPROVED,
    curve_class: CurveClass | None = CurveClass.FULL,
    intercept_kind: InterceptKind = InterceptKind.IC,
    intercept_level: float = 50.0,
    intercept_label: str = "IC50",
) -> tuple[list[DoseResponseCurve], dict[uuid.UUID, Run]]:
    """Build a parallel list of curves + runs for the (MOL_ID, RD_ID) cell.

    Each tuple is ``(run_date, fitted_value)``. Returns both the curve
    list (in the order given) and a ``{run_id: Run}`` dict suitable to
    pass as `run_repo.find_by_ids`'s return.

    Intercept defaults to a single IC50 spec carrying the same numeric
    value as the curve's ``fitted_value`` — keeps the resolver's
    intercept-derived scalar identical to the curve's headline, so tests
    that compare against the latest fitted_value get the right answer.
    """
    curves: list[DoseResponseCurve] = []
    runs: dict[uuid.UUID, Run] = {}
    for run_date, value in dates_and_values:
        run_id = uuid.uuid4()
        intercept = _make_intercept_value(
            kind=intercept_kind,
            level=intercept_level,
            label=intercept_label,
            value=value,
        )
        curves.append(
            _make_curve(
                fitted_value=value,
                run_id=run_id,
                curve_class=curve_class,
                intercept_values=[intercept],
            )
        )
        runs[run_id] = _make_run(run_id=run_id, run_date=run_date, status=status)
    return curves, runs


def _make_service(curve_repo=None, run_repo=None) -> MoleculeActivityService:
    protocol_repo = AsyncMock()
    # find_by_ids returns [] by default — service falls back to "uM" for
    # IC50 unit decoration. Tests that need a specific unit should override.
    protocol_repo.find_by_ids = AsyncMock(return_value=[])

    if run_repo is None:
        run_repo = AsyncMock()
        # Default: no runs registered. Tests that exercise the DR path
        # must override this so `_build_resolved_runs` can adapt curves
        # back to their owning Run (run_date + status).
        run_repo.find_by_ids = AsyncMock(return_value={})

    return MoleculeActivityService(
        uow=_FakeUoW(),
        readout_repo=AsyncMock(),
        curve_repo=curve_repo or AsyncMock(),
        protocol_repo=protocol_repo,
        run_repo=run_repo,
    )


def _curve_repo_for(curves: list[DoseResponseCurve]) -> AsyncMock:
    """Build a curve_repo mock whose `find_all_curves_for_molecules` returns
    the given curves under (MOL_ID, RD_ID), sorted newest-first by run_id
    appearance — the SQL repo sorts by run_date desc, so the caller is
    expected to pass curves already sorted by run_date desc.
    """
    repo = AsyncMock()
    repo.find_all_curves_for_molecules = AsyncMock(
        return_value={MOL_ID: {RD_ID: list(curves)}}
    )
    return repo


def _run_repo_for(runs: dict[uuid.UUID, Run]) -> AsyncMock:
    repo = AsyncMock()
    repo.find_by_ids = AsyncMock(return_value=dict(runs))
    return repo


# ---------------------------------------------------------------------------
# Tests — single-run behavior (curve params + intercept values).
# ---------------------------------------------------------------------------


class TestEnrichMoleculesWithCurveParams:
    """enrich_molecules populates raw_data and curve_params from DoseResponseCurve."""

    @pytest.mark.asyncio
    async def test_curve_params_and_raw_data_populated(self) -> None:
        """ActivityValue should contain condensed raw_data and full curve params."""
        raw_points = [
            {"concentration": 0.01, "response": 95.0},
            {"concentration": 0.1, "response": 80.0},
            {"concentration": 1.0, "response": 50.0},
            {"concentration": 10.0, "response": 10.0},
        ]
        run_id = uuid.uuid4()
        curve = _make_curve(raw_data=raw_points, run_id=run_id)
        runs = {run_id: _make_run(run_id=run_id, run_date=date(2026, 4, 1))}

        service = _make_service(
            curve_repo=_curve_repo_for([curve]),
            run_repo=_run_repo_for(runs),
        )
        col_spec = f"drc:{RD_ID}"

        result = await service.enrich_molecules(WS, [MOL_ID], [col_spec])

        assert MOL_ID in result
        av = result[MOL_ID][col_spec]

        # Basic fields — single-run cell, value comes from the only curve.
        assert av.value == 5.2
        assert av.unit == "uM"
        assert av.source == "dose_response"
        assert av.curve_type == "ic50"
        assert av.r_squared == 0.97
        # data_point_count now reflects the number of raw points on the
        # representative curve (4 here), not num_points from the fit.
        assert av.data_point_count == 4

        # raw_data condensed to [{x, y}]
        assert av.raw_data is not None
        assert len(av.raw_data) == 4
        assert av.raw_data[0] == {"x": 0.01, "y": 95.0}
        assert av.raw_data[3] == {"x": 10.0, "y": 10.0}

        # curve_params
        assert av.curve_params is not None
        assert av.curve_params.hill_slope == -1.1
        assert av.curve_params.top == 100.0
        assert av.curve_params.bottom == 0.5
        # num_points on CurveParams now reflects raw_data length (same
        # source of truth as data_point_count).
        assert av.curve_params.num_points == 4
        assert av.curve_params.curve_class == "full"
        assert av.curve_params.confidence_interval_low == 3.8
        assert av.curve_params.confidence_interval_high == 7.1

        # New multi-run context fields on a single-run cell
        assert av.run_count == 1
        assert av.selection_rule == SelectionRule.LATEST_APPROVED_RUN.value
        assert av.runs is not None and len(av.runs) == 1
        assert av.disagreement_flag is False

    @pytest.mark.asyncio
    async def test_curve_without_raw_data(self) -> None:
        """When raw_data is empty/None, raw_data on ActivityValue is None."""
        run_id = uuid.uuid4()
        curve = _make_curve(raw_data=None, run_id=run_id)
        runs = {run_id: _make_run(run_id=run_id, run_date=date(2026, 4, 1))}

        service = _make_service(
            curve_repo=_curve_repo_for([curve]),
            run_repo=_run_repo_for(runs),
        )
        col_spec = f"drc:{RD_ID}"

        result = await service.enrich_molecules(WS, [MOL_ID], [col_spec])

        av = result[MOL_ID][col_spec]
        assert av.raw_data is None
        # curve_params should still be populated
        assert av.curve_params is not None
        assert av.curve_params.hill_slope == -1.1

    @pytest.mark.asyncio
    async def test_curve_without_curve_class(self) -> None:
        """When curve_class is None, CurveParams.curve_class is None."""
        run_id = uuid.uuid4()
        curve = _make_curve(
            curve_class=None,
            confidence_interval_low=None,
            confidence_interval_high=None,
            run_id=run_id,
        )
        runs = {run_id: _make_run(run_id=run_id, run_date=date(2026, 4, 1))}

        service = _make_service(
            curve_repo=_curve_repo_for([curve]),
            run_repo=_run_repo_for(runs),
        )
        col_spec = f"drc:{RD_ID}"

        result = await service.enrich_molecules(WS, [MOL_ID], [col_spec])

        av = result[MOL_ID][col_spec]
        assert av.curve_params is not None
        assert av.curve_params.curve_class is None
        assert av.curve_params.confidence_interval_low is None
        assert av.curve_params.confidence_interval_high is None


class TestEnrichMoleculesInterceptValues:
    """Per-spec intercepts (EC50/EC90/IC10/...) flow to ActivityValue."""

    @pytest.mark.asyncio
    async def test_intercept_values_serialized_on_dr_activity(self) -> None:
        """DR-source ActivityValue carries the curve's intercept_values list.

        Search results grid keys per-protocol column groups by ``drc:<rd_id>``
        and renders one sub-column per protocol intercept (EC50, EC90, ...).
        Each cell looks up its value by (kind, level) — so the wire payload
        must carry both the spec and the value for every persisted intercept.
        """
        intercepts = [
            InterceptValue(
                spec=InterceptSpec(
                    kind=InterceptKind.EC,
                    level=50.0,
                    basis=InterceptBasis.RELATIVE_PERCENT,
                    label="EC50",
                ),
                value=5.2,
                confidence_interval_low=3.8,
                confidence_interval_high=7.1,
                at_bound=False,
            ),
            InterceptValue(
                spec=InterceptSpec(
                    kind=InterceptKind.EC,
                    level=90.0,
                    basis=InterceptBasis.RELATIVE_PERCENT,
                    label="EC90",
                ),
                value=12.4,
                confidence_interval_low=None,
                confidence_interval_high=None,
                at_bound=True,
            ),
        ]
        run_id = uuid.uuid4()
        curve = _make_curve(intercept_values=intercepts, run_id=run_id)
        runs = {run_id: _make_run(run_id=run_id, run_date=date(2026, 4, 1))}

        service = _make_service(
            curve_repo=_curve_repo_for([curve]),
            run_repo=_run_repo_for(runs),
        )
        col_spec = f"drc:{RD_ID}"

        result = await service.enrich_molecules(WS, [MOL_ID], [col_spec])
        av = result[MOL_ID][col_spec]

        assert av.intercept_values is not None
        assert len(av.intercept_values) == 2

        ec50 = av.intercept_values[0]
        assert ec50["spec"]["kind"] == "ec"
        assert ec50["spec"]["level"] == 50.0
        assert ec50["spec"]["label"] == "EC50"
        assert ec50["value"] == 5.2
        assert ec50["at_bound"] is False

        ec90 = av.intercept_values[1]
        assert ec90["spec"]["level"] == 90.0
        assert ec90["spec"]["label"] == "EC90"
        assert ec90["at_bound"] is True
        assert ec90["confidence_interval_low"] is None

        # Aggregator built one InterceptAggregate per spec.
        assert av.intercept_aggregates is not None
        assert len(av.intercept_aggregates) == 2
        ec50_agg = av.intercept_aggregates[0]
        assert ec50_agg.spec["kind"] == "ec"
        assert ec50_agg.spec["level"] == 50.0
        assert ec50_agg.selected_value == 5.2
        # at_bound on EC90 → resolver flips to GT max-of-raw, ND when no raw.
        ec90_agg = av.intercept_aggregates[1]
        assert ec90_agg.selected_value is None  # no raw_data → ND
        assert ec90_agg.selected_qualifier == "nd"

    @pytest.mark.asyncio
    async def test_intercept_values_none_when_curve_has_none(self) -> None:
        """Legacy curve with no intercept_values yields intercept_values=None."""
        run_id = uuid.uuid4()
        curve = _make_curve(intercept_values=None, run_id=run_id)
        runs = {run_id: _make_run(run_id=run_id, run_date=date(2026, 4, 1))}

        service = _make_service(
            curve_repo=_curve_repo_for([curve]),
            run_repo=_run_repo_for(runs),
        )
        col_spec = f"drc:{RD_ID}"

        result = await service.enrich_molecules(WS, [MOL_ID], [col_spec])
        av = result[MOL_ID][col_spec]
        assert av.intercept_values is None
        # No intercepts → no per-intercept aggregates either; top-level value
        # falls back to the curve's fitted_value through the None-key path.
        assert av.intercept_aggregates is None
        assert av.value == 5.2


class TestEnrichMoleculesEmptyInputs:
    """Edge cases for empty inputs."""

    @pytest.mark.asyncio
    async def test_empty_molecule_ids_returns_empty(self) -> None:
        service = _make_service()
        result = await service.enrich_molecules(WS, [], [f"drc:{RD_ID}"])
        assert result == {}

    @pytest.mark.asyncio
    async def test_empty_columns_returns_empty(self) -> None:
        service = _make_service()
        result = await service.enrich_molecules(WS, [MOL_ID], [])
        assert result == {}

    @pytest.mark.asyncio
    async def test_no_matching_curve_returns_empty(self) -> None:
        """When the curve repo returns no curves for the molecule."""
        curve_repo = AsyncMock()
        curve_repo.find_all_curves_for_molecules = AsyncMock(return_value={})

        service = _make_service(curve_repo=curve_repo)
        col_spec = f"drc:{RD_ID}"

        result = await service.enrich_molecules(WS, [MOL_ID], [col_spec])
        assert result == {}


# ---------------------------------------------------------------------------
# NEW — multi-run aggregation behavior (Task 6).
# ---------------------------------------------------------------------------


class TestEnrichMoleculesMultiRunAggregation:
    """The new aggregator-driven path replaces best-R² cherry-picking."""

    @pytest.mark.asyncio
    async def test_default_uses_latest_approved_run(self) -> None:
        """3 runs: latest fitted IC50 = 0.20 wins under the default rule."""
        # Order matches what the SQL repo returns: newest first.
        curves, runs = _seed_runs(
            [
                (date(2026, 4, 1), 0.20),
                (date(2026, 3, 1), 0.05),
                (date(2026, 1, 1), 0.10),
            ]
        )
        service = _make_service(
            curve_repo=_curve_repo_for(curves),
            run_repo=_run_repo_for(runs),
        )
        col_spec = f"drc:{RD_ID}"

        out = await service.enrich_molecules(WS, [MOL_ID], [col_spec])

        av = out[MOL_ID][col_spec]
        assert av.value == 0.20
        assert av.run_count == 3
        assert av.selection_rule == SelectionRule.LATEST_APPROVED_RUN.value
        assert av.runs is not None and len(av.runs) == 3
        # Tooltip rows are also sorted latest-first.
        assert av.runs[0].run_date == date(2026, 4, 1)

    @pytest.mark.asyncio
    async def test_geometric_mean_aggregates(self) -> None:
        """gmean of 0.10, 0.20, 0.40 = 0.20; fold_range = 0.40/0.10 = 4.0."""
        curves, runs = _seed_runs(
            [
                (date(2026, 4, 1), 0.10),
                (date(2026, 3, 1), 0.20),
                (date(2026, 1, 1), 0.40),
            ]
        )
        service = _make_service(
            curve_repo=_curve_repo_for(curves),
            run_repo=_run_repo_for(runs),
        )
        col_spec = f"drc:{RD_ID}"

        out = await service.enrich_molecules(
            WS,
            [MOL_ID],
            [col_spec],
            selection_rule=SelectionRule.GEOMETRIC_MEAN,
        )

        av = out[MOL_ID][col_spec]
        assert av.value == pytest.approx(0.20, rel=1e-3)
        assert av.selection_rule == SelectionRule.GEOMETRIC_MEAN.value
        assert av.intercept_aggregates is not None
        assert len(av.intercept_aggregates) == 1
        stats = av.intercept_aggregates[0].aggregate_stats
        assert stats is not None
        assert stats.geometric_mean == pytest.approx(0.20, rel=1e-3)
        assert stats.fold_range == pytest.approx(4.0)

    @pytest.mark.asyncio
    async def test_run_scope_caps_input(self) -> None:
        """last_n=2 → only 2 curves are passed to the aggregator."""
        # The SQL repo applies last_n itself; the service trusts what the
        # repo returns. Mock returns only 2 curves to mirror that contract.
        curves, runs = _seed_runs(
            [
                (date(2026, 4, 1), 0.10),
                (date(2026, 3, 1), 0.20),
            ]
        )
        # All 5 runs registered in run_repo (defensive — only the 2 returned
        # ones are looked up), 2 returned by curve_repo.
        service = _make_service(
            curve_repo=_curve_repo_for(curves),
            run_repo=_run_repo_for(runs),
        )
        col_spec = f"drc:{RD_ID}"

        out = await service.enrich_molecules(
            WS,
            [MOL_ID],
            [col_spec],
            run_scopes={col_spec: RunScope.last_n(2)},
        )

        av = out[MOL_ID][col_spec]
        assert av.run_count == 2

        # Verify the scope was passed through to the repo call.
        service._curve_repo.find_all_curves_for_molecules.assert_awaited_once()
        kwargs = service._curve_repo.find_all_curves_for_molecules.await_args.kwargs
        assert kwargs["run_scope"] == RunScope.last_n(2)

    @pytest.mark.asyncio
    async def test_inactive_runs_trigger_disagreement(self) -> None:
        """2 active EQ runs + 1 Inactive run → disagreement_flag=True on the cell."""
        # Two healthy + one inactive; latest is healthy so cell still has a value.
        active_a, runs_a = _seed_runs(
            [(date(2026, 4, 1), 0.20), (date(2026, 3, 1), 0.40)]
        )
        inactive, runs_inactive = _seed_runs(
            [(date(2026, 1, 1), 0.10)], curve_class=CurveClass.INACTIVE
        )
        curves = active_a + inactive
        runs = {**runs_a, **runs_inactive}

        service = _make_service(
            curve_repo=_curve_repo_for(curves),
            run_repo=_run_repo_for(runs),
        )
        col_spec = f"drc:{RD_ID}"

        out = await service.enrich_molecules(WS, [MOL_ID], [col_spec])

        av = out[MOL_ID][col_spec]
        assert av.disagreement_flag is True
        assert av.intercept_aggregates is not None
        assert av.intercept_aggregates[0].disagreement_flag is True

    @pytest.mark.asyncio
    async def test_runs_payload_capped_at_10(self) -> None:
        """run_count carries the full history; runs[] is bounded to 10 entries."""
        # 15 runs, distinct dates so sort order is deterministic.
        seeds = [
            (date(2025, 1 + (i % 12), 1 + (i // 12)), 0.5 + i * 0.01) for i in range(15)
        ]
        curves, runs = _seed_runs(seeds)
        service = _make_service(
            curve_repo=_curve_repo_for(curves),
            run_repo=_run_repo_for(runs),
        )
        col_spec = f"drc:{RD_ID}"

        out = await service.enrich_molecules(WS, [MOL_ID], [col_spec])

        av = out[MOL_ID][col_spec]
        assert av.run_count == 15
        assert av.runs is not None and len(av.runs) == 10
