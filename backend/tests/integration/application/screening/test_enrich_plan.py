"""MoleculeActivityService over a ColumnPlan — one run-set calculation for every search cell.

Real database: the values come from the SQL read queries and the shared run
aggregator together, exactly as search, export and SAR use them.
"""

from __future__ import annotations

import uuid
from datetime import date

import pytest

from cellar.application.screening.molecule_activity_service import MoleculeActivityService
from cellar.domain.screening_assay.run_scope import RunScope
from cellar.domain.shared.aggregation_types import SelectionRule
from cellar.infrastructure.persistence.sqlalchemy.screening_assay.dose_response_curve_repository import (
    SQLAlchemyDoseResponseCurveRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.screening_assay.protocol_repository import (
    SQLAlchemyProtocolRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.screening_assay.readout_data_repository import (
    SQLAlchemyReadoutDataRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.screening_assay.run_repository import (
    SQLAlchemyRunRepository,
)
from tests.integration import _screening_seed as seed

pytestmark = pytest.mark.asyncio

JAN, FEB, MAR, APR = date(2026, 1, 1), date(2026, 2, 1), date(2026, 3, 1), date(2026, 4, 1)
MOL = uuid.UUID("00000000-0000-0000-0000-00000000a001")


def _service(uow) -> MoleculeActivityService:
    return MoleculeActivityService(
        uow=uow,
        readout_repo=SQLAlchemyReadoutDataRepository(uow),
        curve_repo=SQLAlchemyDoseResponseCurveRepository(uow),
        protocol_repo=SQLAlchemyProtocolRepository(uow),
        run_repo=SQLAlchemyRunRepository(uow),
    )


async def _enrich(uow, ws, tokens, *, rule=SelectionRule.LATEST_RUN, scopes=None, criteria=None):
    service = _service(uow)
    async with uow:
        if criteria is None:
            plan = await service.planner.plan_from_scopes(ws, tokens, scopes or {})
        else:

            async def matching():
                return [MOL]

            plan = await service.planner.plan(ws, tokens, criteria=criteria, matching_ids=matching)
        out = await service.enrich_plan(ws, [MOL], plan, selection_rule=rule)
    return out.get(MOL, {})


# --- single-point columns (R2, R3) --------------------------------------------------


@pytest.fixture
async def percent_runs(uow, workspace_id):
    """% inhibition: Jan wells 10, 20 · Feb well 80 · Apr (rejected) well 99."""
    async with uow:
        s = uow.session
        p = await seed.protocol(s, workspace_id)
        rd = await seed.readout_def(s, p, name="% Inhibition", unit="%")
        jan = await seed.run(s, workspace_id, p, JAN)
        feb = await seed.run(s, workspace_id, p, FEB)
        apr = await seed.run(s, workspace_id, p, APR, status="rejected")
        for v in (10.0, 20.0):
            await seed.readout(s, workspace_id, jan, rd, MOL, v)
        await seed.readout(s, workspace_id, feb, rd, MOL, 80.0)
        await seed.readout(s, workspace_id, apr, rd, MOL, 99.0)
        await uow.commit()
    return {"token": f"rd:{p}:{rd}", "jan": jan, "feb": feb}


async def test_single_point_latest_run_is_the_newest_non_rejected_run(
    uow, workspace_id, percent_runs
):
    cells = await _enrich(uow, workspace_id, [percent_runs["token"]])
    av = cells[percent_runs["token"]]
    assert av.value == pytest.approx(80.0)
    assert av.source == "readout"
    assert av.run_count == 2
    assert av.run_ids == [percent_runs["feb"], percent_runs["jan"]]


async def test_single_point_mean_averages_runs_not_wells(uow, workspace_id, percent_runs):
    cells = await _enrich(
        uow, workspace_id, [percent_runs["token"]], rule=SelectionRule.MEAN_ACROSS_RUNS
    )
    # Jan's run value is 15 (mean of its wells); pooled wells would give 36.7.
    assert cells[percent_runs["token"]].value == pytest.approx((15.0 + 80.0) / 2)


async def test_geomean_on_a_percent_column_is_the_arithmetic_mean(uow, workspace_id, percent_runs):
    cells = await _enrich(
        uow, workspace_id, [percent_runs["token"]], rule=SelectionRule.GEOMETRIC_MEAN
    )
    av = cells[percent_runs["token"]]
    assert av.value == pytest.approx(47.5)
    assert av.selection_rule == SelectionRule.MEAN_ACROSS_RUNS.value


async def test_best_fit_on_a_single_point_column_is_the_latest_run(
    uow, workspace_id, percent_runs
):
    cells = await _enrich(
        uow, workspace_id, [percent_runs["token"]], rule=SelectionRule.BEST_R_SQUARED
    )
    assert cells[percent_runs["token"]].value == pytest.approx(80.0)


async def test_single_point_cells_carry_their_run_history(uow, workspace_id, percent_runs):
    av = (await _enrich(uow, workspace_id, [percent_runs["token"]]))[percent_runs["token"]]
    assert [(r.run_date, r.intercept_values[0]["value"]) for r in av.runs] == [
        (FEB, pytest.approx(80.0)),
        (JAN, pytest.approx(15.0)),
    ]
    assert all(r.curve_id is None for r in av.runs)


# --- dose-response columns (R3, R4, R9) -----------------------------------------------


@pytest.fixture
async def dr(uow, workspace_id):
    async with uow:
        s = uow.session
        p = await seed.protocol(s, workspace_id, dose_unit="nM")
        rd = await seed.readout_def(s, p, name="IC50", data_type="dose_response", unit="nM")
        await uow.commit()
    return {"p": p, "rd": rd, "token": f"drc:{rd}"}


async def test_dr_latest_run_ignores_a_rejected_newer_run(uow, workspace_id, dr):
    async with uow:
        s = uow.session
        jan = await seed.run(s, workspace_id, dr["p"], JAN)
        apr = await seed.run(s, workspace_id, dr["p"], APR, status="rejected")
        kept = await seed.curve(s, workspace_id, dr["p"], jan, MOL, dr["rd"], fitted_value=5.0)
        await seed.curve(s, workspace_id, dr["p"], apr, MOL, dr["rd"], fitted_value=0.1)
        await uow.commit()

    av = (await _enrich(uow, workspace_id, [dr["token"]]))[dr["token"]]
    assert av.value == pytest.approx(5.0)
    assert av.unit == "nM"
    assert av.representative_curve_id == kept
    assert av.run_ids == [jan]


async def test_reported_endpoint_is_used_only_without_a_curve(uow, workspace_id, dr):
    async with uow:
        s = uow.session
        jan = await seed.run(s, workspace_id, dr["p"], JAN)
        await seed.readout(s, workspace_id, jan, dr["rd"], MOL, 3.4, wellless=True)
        await uow.commit()
    av = (await _enrich(uow, workspace_id, [dr["token"]]))[dr["token"]]
    assert (av.value, av.source) == (pytest.approx(3.4), "readout")
    # No fit behind a reported value: the curve fields stay empty.
    assert (av.curve_params, av.raw_data, av.representative_curve_id) == (None, None, None)

    async with uow:
        s = uow.session
        feb = await seed.run(s, workspace_id, dr["p"], FEB)
        await seed.curve(s, workspace_id, dr["p"], feb, MOL, dr["rd"], fitted_value=7.0)
        await uow.commit()
    av = (await _enrich(uow, workspace_id, [dr["token"]]))[dr["token"]]
    assert (av.value, av.source) == (pytest.approx(7.0), "dose_response")


async def test_reported_endpoint_respects_a_specific_run_filter(uow, workspace_id, dr):
    async with uow:
        s = uow.session
        a = await seed.run(s, workspace_id, dr["p"], JAN)
        b = await seed.run(s, workspace_id, dr["p"], FEB)
        await seed.readout(s, workspace_id, a, dr["rd"], MOL, 3.4, wellless=True)
        await seed.readout(s, workspace_id, b, dr["rd"], MOL, 9.9, wellless=True)
        await uow.commit()
    cells = await _enrich(
        uow, workspace_id, [dr["token"]], scopes={dr["token"]: RunScope.run_ids([a])}
    )
    assert cells[dr["token"]].value == pytest.approx(3.4)


async def test_a_reported_greater_than_stays_qualified(uow, workspace_id, dr):
    async with uow:
        s = uow.session
        jan = await seed.run(s, workspace_id, dr["p"], JAN)
        await seed.readout(s, workspace_id, jan, dr["rd"], MOL, 50.0, qualifier=">", wellless=True)
        await uow.commit()
    av = (await _enrich(uow, workspace_id, [dr["token"]]))[dr["token"]]
    assert (av.value, av.qualifier) == (pytest.approx(50.0), ">")


async def test_mean_of_only_qualified_runs_is_nd(uow, workspace_id, dr):
    async with uow:
        s = uow.session
        for d in (JAN, FEB):
            r = await seed.run(s, workspace_id, dr["p"], d)
            await seed.readout(
                s, workspace_id, r, dr["rd"], MOL, 50.0, qualifier=">", wellless=True
            )
        await uow.commit()
    av = (await _enrich(uow, workspace_id, [dr["token"]], rule=SelectionRule.MEAN_ACROSS_RUNS))[
        dr["token"]
    ]
    assert (av.value, av.qualifier) == (None, "nd")


# --- splits ---------------------------------------------------------------------------


async def test_split_by_condition_gives_one_cell_per_group(uow, workspace_id):
    async with uow:
        s = uow.session
        p = await seed.protocol(s, workspace_id, conditions=[("ATP", "numeric", "uM")])
        rd = await seed.readout_def(s, p, data_type="dose_response")
        low = await seed.run(s, workspace_id, p, JAN, conditions={"ATP": "10 uM"})
        high = await seed.run(s, workspace_id, p, FEB, conditions={"ATP": "1 mM"})
        await seed.curve(s, workspace_id, p, low, MOL, rd, fitted_value=30.0)
        await seed.curve(s, workspace_id, p, high, MOL, rd, fitted_value=210.0)
        await uow.commit()

    token = f"drc:{rd}"
    criteria = [
        {
            "type": "activity",
            "protocol_id": str(p),
            "split": {"by": "condition", "condition": "ATP"},
        }
    ]
    cells = await _enrich(uow, workspace_id, [token], criteria=criteria)
    assert {k: v.value for k, v in cells.items()} == {
        f"{token}@cond:10 µM": pytest.approx(30.0),
        f"{token}@cond:1 mM": pytest.approx(210.0),
    }


async def test_unsplit_columns_keep_their_token_keys(uow, workspace_id, percent_runs):
    cells = await _enrich(uow, workspace_id, [percent_runs["token"]])
    assert list(cells) == [percent_runs["token"]]


# --- the "Active in" column ----------------------------------------------------------------


async def test_any_column_ignores_rejected_runs(uow, workspace_id, dr):
    async with uow:
        s = uow.session
        apr = await seed.run(s, workspace_id, dr["p"], APR, status="rejected")
        await seed.curve(s, workspace_id, dr["p"], apr, MOL, dr["rd"], fitted_value=0.1)
        await uow.commit()
    assert "any" not in await _enrich(uow, workspace_id, ["any"])


# --- final-review fixes ----------------------------------------------------------------


def _ic50(value, *, at_bound=False):
    spec = {"kind": "ic", "level": 50.0, "basis": "relative_percent", "label": None}
    return [{"spec": spec, "value": value, "at_bound": at_bound}]


async def test_lean_cells_resolve_an_at_bound_run_like_full_cells(uow, workspace_id, dr):
    """Sorting uses lean cells; they must show the same >max-dose bound as the grid."""
    async with uow:
        s = uow.session
        jan = await seed.run(s, workspace_id, dr["p"], JAN)
        apr = await seed.run(s, workspace_id, dr["p"], APR)
        await seed.curve(
            s,
            workspace_id,
            dr["p"],
            jan,
            MOL,
            dr["rd"],
            fitted_value=5.0,
            intercept_values=_ic50(5.0),
        )
        await seed.curve(
            s,
            workspace_id,
            dr["p"],
            apr,
            MOL,
            dr["rd"],
            fitted_value=150.0,
            intercept_values=_ic50(150.0, at_bound=True),
            max_dose=100.0,
        )
        await uow.commit()

    service = _service(uow)
    async with uow:
        plan = await service.planner.plan_from_scopes(workspace_id, [dr["token"]], {})
        full = await service.enrich_plan(workspace_id, [MOL], plan)
        lean = await service.enrich_plan(workspace_id, [MOL], plan, lean=True)
    for cells in (full, lean):
        av = cells[MOL][dr["token"]]
        assert (av.value, av.qualifier) == (pytest.approx(100.0), ">")


async def test_reported_endpoint_cell_stands_for_the_primary_intercept(uow, workspace_id, dr):
    async with uow:
        s = uow.session
        jan = await seed.run(s, workspace_id, dr["p"], JAN)
        await seed.readout(s, workspace_id, jan, dr["rd"], MOL, 3.4, wellless=True)
        await uow.commit()
    av = (await _enrich(uow, workspace_id, [dr["token"]]))[dr["token"]]
    (agg,) = av.intercept_aggregates
    assert (agg.spec["kind"], agg.spec["level"]) == ("ic", 50.0)
    assert (agg.selected_value, agg.selected_qualifier) == (pytest.approx(3.4), "=")


async def test_approximate_readouts_count_as_values(uow, workspace_id, percent_runs):
    async with uow:
        s = uow.session
        p = await seed.protocol(s, workspace_id)
        rd = await seed.readout_def(s, p, unit="%")
        r = await seed.run(s, workspace_id, p, JAN)
        await seed.readout(s, workspace_id, r, rd, MOL, 42.0, qualifier="~")
        await uow.commit()
    token = f"rd:{p}:{rd}"
    av = (await _enrich(uow, workspace_id, [token]))[token]
    assert (av.value, av.qualifier) == (pytest.approx(42.0), None)


async def test_latest_run_tie_is_broken_the_same_way_everywhere(uow, workspace_id, dr):
    """Two runs with the same date and creation time: values and matching agree."""
    from datetime import datetime

    from cellar.infrastructure.persistence.sqlalchemy.chemical_registration.molecule_reader import (
        SQLAlchemyMoleculeReader,
    )

    created = datetime(2026, 1, 1, 12, 0)
    async with uow:
        s = uow.session
        o = await seed.org(s, workspace_id)
        a = await seed.molecule(s, workspace_id, o, "a", **seed.descriptors(300.0))
        b = await seed.molecule(s, workspace_id, o, "b", **seed.descriptors(300.0))
        r1 = await seed.run(s, workspace_id, dr["p"], JAN, created_at=created)
        r2 = await seed.run(s, workspace_id, dr["p"], JAN, created_at=created)
        await seed.curve(s, workspace_id, dr["p"], r1, a, dr["rd"], fitted_value=1.0)
        await seed.curve(s, workspace_id, dr["p"], r2, b, dr["rd"], fitted_value=2.0)
        await uow.commit()
    winner = b if str(r2) > str(r1) else a

    cells = {}
    service = _service(uow)
    async with uow:
        plan = await service.planner.plan_from_scopes(
            workspace_id, [dr["token"]], {dr["token"]: RunScope.latest_of_protocol()}
        )
        cells = await service.enrich_plan(workspace_id, [a, b], plan)
    reader = SQLAlchemyMoleculeReader(uow._session_factory)
    query = {
        "logic": "and",
        "criteria": [
            {"type": "activity", "protocol_id": str(dr["p"]), "run_scope": {"mode": "latest"}}
        ],
    }
    matched = {m.id for m in await reader.search_by_query(workspace_id, query)}
    assert set(cells) == {winner}
    assert matched == {winner}


async def test_an_end_date_alone_narrows_values_like_matching(uow, workspace_id, percent_runs):
    scope = RunScope.from_wire({"mode": "date_range", "date_to": "2026-01-15"})
    cells = await _enrich(
        uow, workspace_id, [percent_runs["token"]], scopes={percent_runs["token"]: scope}
    )
    assert cells[percent_runs["token"]].run_ids == [percent_runs["jan"]]
