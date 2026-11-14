"""Read queries behind search columns: per-run readout stats, run headers, curves, ranked ids."""

from __future__ import annotations

import uuid
from datetime import date

import pytest

from cellar.domain.screening_assay.run_scope import RunScope
from cellar.infrastructure.persistence.sqlalchemy.chemical_registration.molecule_reader import (
    SQLAlchemyMoleculeReader,
)
from cellar.infrastructure.persistence.sqlalchemy.screening_assay.dose_response_curve_repository import (
    SQLAlchemyDoseResponseCurveRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.screening_assay.readout_data_repository import (
    SQLAlchemyReadoutDataRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.screening_assay.run_repository import (
    SQLAlchemyRunRepository,
)
from tests.integration import _screening_seed as seed

pytestmark = pytest.mark.asyncio

JAN, FEB, APR = date(2026, 1, 1), date(2026, 2, 1), date(2026, 4, 1)


# --- per-run readout stats ---------------------------------------------------


async def test_run_stats_one_row_per_run(uow, workspace_id):
    mol = uuid.uuid4()
    async with uow:
        s = uow.session
        p = await seed.protocol(s, workspace_id)
        rd = await seed.readout_def(s, p, unit="%", aggregation="mean")
        r1 = await seed.run(s, workspace_id, p, JAN)
        r2 = await seed.run(s, workspace_id, p, FEB)
        for v in (10.0, 20.0):
            await seed.readout(s, workspace_id, r1, rd, mol, v)
        await seed.readout(s, workspace_id, r2, rd, mol, 80.0)
        await uow.commit()

    async with uow:
        rows = await SQLAlchemyReadoutDataRepository(uow).find_run_stats(
            workspace_id, [mol], [(rd, None)], run_scope=RunScope.all()
        )

    by_run = {r.run_id: r for r in rows}
    assert set(by_run) == {r1, r2}
    assert by_run[r1].stats.eq_count == 2
    assert by_run[r1].stats.eq_mean == pytest.approx(15.0)
    assert by_run[r2].stats.eq_mean == pytest.approx(80.0)
    assert by_run[r1].run_date == JAN
    assert by_run[r1].unit == "%"
    assert by_run[r1].aggregation == "mean"
    assert by_run[r1].protocol_id == p


async def test_run_stats_exclude_rejected_runs_and_outliers(uow, workspace_id):
    mol = uuid.uuid4()
    async with uow:
        s = uow.session
        p = await seed.protocol(s, workspace_id)
        rd = await seed.readout_def(s, p)
        ok = await seed.run(s, workspace_id, p, JAN)
        bad = await seed.run(s, workspace_id, p, FEB, status="rejected")
        await seed.readout(s, workspace_id, ok, rd, mol, 10.0)
        await seed.readout(s, workspace_id, ok, rd, mol, 999.0, outlier=True)
        await seed.readout(s, workspace_id, bad, rd, mol, 50.0)
        await uow.commit()

    async with uow:
        rows = await SQLAlchemyReadoutDataRepository(uow).find_run_stats(
            workspace_id, [mol], [(rd, None)], run_scope=RunScope.all()
        )

    assert [(r.run_id, r.stats.eq_count, r.stats.eq_max) for r in rows] == [(ok, 1, 10.0)]


async def test_run_stats_real_median_and_geomean(uow, workspace_id):
    mol = uuid.uuid4()
    async with uow:
        s = uow.session
        p = await seed.protocol(s, workspace_id)
        rd = await seed.readout_def(s, p, unit="uM", aggregation="median")
        r = await seed.run(s, workspace_id, p, JAN)
        for v in (1.0, 2.0, 100.0):
            await seed.readout(s, workspace_id, r, rd, mol, v)
        await uow.commit()

    async with uow:
        (row,) = await SQLAlchemyReadoutDataRepository(uow).find_run_stats(
            workspace_id, [mol], [(rd, None)], run_scope=RunScope.all()
        )

    assert row.stats.eq_median == pytest.approx(2.0)
    assert row.stats.eq_mean == pytest.approx(103.0 / 3)
    assert row.stats.eq_geomean == pytest.approx((1.0 * 2.0 * 100.0) ** (1 / 3))


async def test_run_stats_qualifier_bounds(uow, workspace_id):
    mol = uuid.uuid4()
    async with uow:
        s = uow.session
        p = await seed.protocol(s, workspace_id)
        rd = await seed.readout_def(s, p, unit="uM")
        r = await seed.run(s, workspace_id, p, JAN)
        await seed.readout(s, workspace_id, r, rd, mol, 12.0, qualifier="=")
        await seed.readout(s, workspace_id, r, rd, mol, 25.0, qualifier=">")
        await seed.readout(s, workspace_id, r, rd, mol, 50.0, qualifier=">=")
        await seed.readout(s, workspace_id, r, rd, mol, 0.1, qualifier="<")
        await seed.readout(s, workspace_id, r, rd, mol, 0.2, qualifier="<=")
        await uow.commit()

    async with uow:
        (row,) = await SQLAlchemyReadoutDataRepository(uow).find_run_stats(
            workspace_id, [mol], [(rd, None)], run_scope=RunScope.all()
        )

    st = row.stats
    assert (st.eq_count, st.eq_mean) == (1, 12.0)
    assert (st.gt_count, st.gt_max_bound) == (2, 50.0)
    assert (st.lt_count, st.lt_min_bound) == (2, 0.1)


async def test_run_stats_respect_specific_and_latest_scopes(uow, workspace_id):
    mol = uuid.uuid4()
    async with uow:
        s = uow.session
        p = await seed.protocol(s, workspace_id)
        rd = await seed.readout_def(s, p)
        r_jan = await seed.run(s, workspace_id, p, JAN)
        r_apr = await seed.run(s, workspace_id, p, APR)
        await seed.run(s, workspace_id, p, date(2026, 5, 1), status="rejected")
        await seed.readout(s, workspace_id, r_jan, rd, mol, 1.0)
        await seed.readout(s, workspace_id, r_apr, rd, mol, 2.0)
        await uow.commit()

    repo = SQLAlchemyReadoutDataRepository(uow)
    async with uow:
        specific = await repo.find_run_stats(
            workspace_id, [mol], [(rd, None)], run_scope=RunScope.run_ids([r_jan])
        )
        latest = await repo.find_run_stats(
            workspace_id, [mol], [(rd, None)], run_scope=RunScope.latest_of_protocol()
        )

    assert [r.run_id for r in specific] == [r_jan]
    assert [r.run_id for r in latest] == [r_apr]


async def test_run_stats_wellless_only_and_normalization(uow, workspace_id):
    mol = uuid.uuid4()
    async with uow:
        s = uow.session
        p = await seed.protocol(s, workspace_id)
        rd = await seed.readout_def(s, p)
        r = await seed.run(s, workspace_id, p, JAN)
        await seed.readout(s, workspace_id, r, rd, mol, 3.0, wellless=True)
        await seed.readout(s, workspace_id, r, rd, mol, 70.0)
        await seed.readout(s, workspace_id, r, rd, mol, 55.0, normalization="percent_inhibition")
        await uow.commit()

    repo = SQLAlchemyReadoutDataRepository(uow)
    async with uow:
        wellless = await repo.find_run_stats(
            workspace_id, [mol], [(rd, None)], run_scope=RunScope.all(), wellless_only=True
        )
        normalized = await repo.find_run_stats(
            workspace_id, [mol], [(rd, "percent_inhibition")], run_scope=RunScope.all()
        )

    assert [r.stats.eq_mean for r in wellless] == [3.0]
    assert [(r.normalization, r.stats.eq_mean) for r in normalized] == [
        ("percent_inhibition", 55.0)
    ]


# --- curves --------------------------------------------------------------------


async def test_curves_exclude_rejected_when_asked_and_lean_keeps_the_tested_range(
    uow, workspace_id
):
    mol = uuid.uuid4()
    async with uow:
        s = uow.session
        p = await seed.protocol(s, workspace_id)
        rd = await seed.readout_def(s, p, data_type="dose_response")
        ok = await seed.run(s, workspace_id, p, JAN)
        bad = await seed.run(s, workspace_id, p, FEB, status="rejected")
        kept = await seed.curve(s, workspace_id, p, ok, mol, rd)
        await seed.curve(s, workspace_id, p, bad, mol, rd)
        await uow.commit()

    repo = SQLAlchemyDoseResponseCurveRepository(uow)
    async with uow:
        everything = await repo.find_all_curves_for_molecules(workspace_id, [mol])
        filtered = await repo.find_all_curves_for_molecules(
            workspace_id, [mol], exclude_rejected=True, lean=True
        )

    assert len(everything[mol][rd]) == 2
    assert [c.id for c in filtered[mol][rd]] == [kept]
    # An at-bound fit resolves to "> max tested dose": lean cells need the points.
    assert filtered[mol][rd][0].raw_data
    assert filtered[mol][rd][0].excluded_points is None


async def test_curves_accept_more_ids_than_the_bind_parameter_limit(uow, workspace_id):
    mol = uuid.uuid4()
    async with uow:
        s = uow.session
        p = await seed.protocol(s, workspace_id)
        rd = await seed.readout_def(s, p, data_type="dose_response")
        r = await seed.run(s, workspace_id, p, JAN)
        await seed.curve(s, workspace_id, p, r, mol, rd)
        await uow.commit()

    ids = [uuid.uuid4() for _ in range(40_000)] + [mol]
    async with uow:
        grouped = await SQLAlchemyDoseResponseCurveRepository(uow).find_all_curves_for_molecules(
            workspace_id, ids
        )
    assert list(grouped) == [mol]


# --- run headers -------------------------------------------------------------------


async def test_runs_measuring_only_non_rejected_runs_with_data_for_the_ids(uow, workspace_id):
    mol, other = uuid.uuid4(), uuid.uuid4()
    async with uow:
        s = uow.session
        p = await seed.protocol(s, workspace_id)
        rd = await seed.readout_def(s, p)
        dr = await seed.readout_def(s, p, data_type="dose_response")
        by_readout = await seed.run(s, workspace_id, p, JAN, conditions={"ATP": "10 uM"})
        by_curve = await seed.run(s, workspace_id, p, FEB, conditions={"ATP": "1 mM"})
        others_only = await seed.run(s, workspace_id, p, APR)
        rejected = await seed.run(s, workspace_id, p, APR, status="rejected")
        await seed.readout(s, workspace_id, by_readout, rd, mol, 1.0)
        await seed.curve(s, workspace_id, p, by_curve, mol, dr)
        await seed.readout(s, workspace_id, others_only, rd, other, 1.0)
        await seed.readout(s, workspace_id, rejected, rd, mol, 1.0)
        await uow.commit()

    async with uow:
        headers = await SQLAlchemyRunRepository(uow).find_runs_measuring(
            workspace_id, p, [mol], run_scope=RunScope.all()
        )

    assert {h.id: h.conditions for h in headers} == {
        by_readout: {"ATP": "10 uM"},
        by_curve: {"ATP": "1 mM"},
    }


async def test_run_headers_carry_status_and_barcodes(uow, workspace_id):
    async with uow:
        s = uow.session
        p = await seed.protocol(s, workspace_id)
        r = await seed.run(s, workspace_id, p, JAN, status="rejected")
        await uow.commit()

    async with uow:
        headers = await SQLAlchemyRunRepository(uow).find_headers(workspace_id, [r, uuid.uuid4()])

    assert list(headers) == [r]
    h = headers[r]
    assert (h.run_date, h.status, h.protocol_id, h.plate_barcodes) == (JAN, "rejected", p, [])


# --- ranked ids ---------------------------------------------------------------------


async def test_ranked_ids_property_sort_nulls_last_and_ordered_fetch(
    session_factory, uow, workspace_id
):
    async with uow:
        s = uow.session
        o = await seed.org(s, workspace_id)
        heavy = await seed.molecule(
            s, workspace_id, o, "heavy", logd=3.0, **seed.descriptors(500.0)
        )
        light = await seed.molecule(
            s, workspace_id, o, "light", logd=1.0, **seed.descriptors(100.0)
        )
        unknown = await seed.molecule(s, workspace_id, o, "unknown", **seed.descriptors(300.0))
        await uow.commit()

    reader = SQLAlchemyMoleculeReader(session_factory)
    query = {"logic": "and", "criteria": []}
    asc = await reader.ranked_ids_by_query(workspace_id, query, sort_by="logd")
    desc = await reader.ranked_ids_by_query(workspace_id, query, sort_by="logd", sort_dir="desc")
    by_id = await reader.ranked_ids_by_query(workspace_id, query)

    assert [i for i, _ in asc] == [light, heavy, unknown]
    assert [i for i, _ in desc] == [heavy, light, unknown]
    assert [i for i, _ in by_id] == sorted([heavy, light, unknown])

    mols = await reader.find_by_ids_ordered(workspace_id, [unknown, heavy, light])
    assert [m.id for m in mols] == [unknown, heavy, light]


async def test_ranked_ids_reject_unknown_sort_field(session_factory, workspace_id):
    reader = SQLAlchemyMoleculeReader(session_factory)
    with pytest.raises(ValueError, match="sort"):
        await reader.ranked_ids_by_query(
            workspace_id, {"logic": "and", "criteria": []}, sort_by="smiles"
        )


# --- readout definition → protocol ---------------------------------------------------


async def test_protocol_ids_by_readout_definition_are_workspace_scoped(uow, workspace_id):
    other_ws = uuid.uuid4()
    async with uow:
        s = uow.session
        p = await seed.protocol(s, workspace_id)
        rd = await seed.readout_def(s, p)
        foreign_p = await seed.protocol(s, other_ws)
        foreign_rd = await seed.readout_def(s, foreign_p)
        await uow.commit()

    from cellar.infrastructure.persistence.sqlalchemy.screening_assay.protocol_repository import (
        SQLAlchemyProtocolRepository,
    )

    async with uow:
        found = await SQLAlchemyProtocolRepository(uow).find_ids_by_readout_definition_ids(
            workspace_id, [rd, foreign_rd, uuid.uuid4()]
        )
    assert found == {rd: p}


async def test_readout_definitions_by_name_match_normalized_name_and_canonical_unit(
    uow, workspace_id
):
    async with uow:
        s = uow.session
        p1 = await seed.protocol(s, workspace_id)
        p2 = await seed.protocol(s, workspace_id)
        hit1 = await seed.readout_def(s, p1, name="% Inhibition", unit="%")
        hit2 = await seed.readout_def(s, p2, name="  % inhibition ", unit="%")
        await seed.readout_def(s, p2, name="% Inhibition", unit="µM")
        foreign = await seed.protocol(s, uuid.uuid4())
        await seed.readout_def(s, foreign, name="% Inhibition", unit="%")
        await uow.commit()

    async with uow:
        found = await SQLAlchemyReadoutDataRepository(uow).find_readout_definitions_by_names(
            workspace_id, [("% inhibition", "%")]
        )
    assert found == {hit1: p1, hit2: p2}
