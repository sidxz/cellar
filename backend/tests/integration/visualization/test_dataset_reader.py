"""SQLAlchemyVisualizationDatasetReader: well values with their context, workspace-scoped."""

from __future__ import annotations

import uuid
from datetime import date

import pytest
import sqlalchemy as sa

from cellar.infrastructure.persistence.sqlalchemy.visualization.dataset_reader import (
    SQLAlchemyVisualizationDatasetReader,
)
from tests.integration import _screening_seed as seed

pytestmark = pytest.mark.asyncio


async def _world(uow, ws: uuid.UUID) -> dict[str, uuid.UUID]:
    """Protocol with one run: plate 1 has B03 (sample, two layers) and A01 (neg control);
    plus one well-less summary row."""
    async with uow:
        s = uow.session
        o = await seed.org(s, ws)
        mol = await seed.molecule(s, ws, o, "m1")
        batch = await seed.batch(s, ws, mol, "B-01")
        p = await seed.protocol(s, ws)
        rd = await seed.readout_def(s, p, name="Signal", unit="AU")
        run = await seed.run(s, ws, p, date(2026, 11, 12), status="approved")
        plate = await seed.plate(s, run, 1, barcode="BC-1")
        b03 = await seed.well(s, plate, "B", 3, dose=10.0, batch_id=batch)
        a01 = await seed.well(s, plate, "A", 1, well_type="negative_control")
        await seed.readout(s, ws, run, rd, mol, 0.42, well_id=b03, batch_id=batch)
        await seed.readout(
            s,
            ws,
            run,
            rd,
            mol,
            61.0,
            well_id=b03,
            batch_id=batch,
            normalization="percent_inhibition",
        )
        await seed.readout(s, ws, run, rd, None, 0.61, well_id=a01)  # type: ignore[arg-type]
        await seed.readout(s, ws, run, rd, mol, 0.5, wellless=True, qualifier=">")
        await uow.commit()
    return {"p": p, "rd": rd, "run": run, "plate": plate, "b03": b03, "a01": a01, "mol": mol}


async def test_well_values_carry_plate_well_compound_and_batch(uow, session_factory, workspace_id):
    w = await _world(uow, workspace_id)
    reader = SQLAlchemyVisualizationDatasetReader(session_factory)

    rows = await reader.fetch_well_values(workspace_id, [w["run"]])

    assert len(rows) == 4
    b03 = [r for r in rows if r.well_id == w["b03"]]
    assert {r.normalization_applied for r in b03} == {None, "percent_inhibition"}
    r = b03[0]
    assert (r.plate_number, r.plate_barcode, r.plate_format) == (1, "BC-1", "384")
    assert (r.well_row, r.well_column, r.well_type, r.dose) == ("B", 3, "sample", 10.0)
    assert r.molecule_id == w["mol"] and r.registration_number and r.smiles == "CCO"
    assert r.batch_number == "B-01"
    control = next(r for r in rows if r.well_id == w["a01"])
    assert control.well_type == "negative_control" and control.molecule_id is None


async def test_wellless_row_has_no_plate_or_well(uow, session_factory, workspace_id):
    w = await _world(uow, workspace_id)
    reader = SQLAlchemyVisualizationDatasetReader(session_factory)

    rows = await reader.fetch_well_values(workspace_id, [w["run"]])

    wellless = [r for r in rows if r.well_id is None]
    assert len(wellless) == 1
    r = wellless[0]
    assert r.plate_id is None and r.well_row is None and r.plate_number is None
    assert r.value_qualifier == ">" and r.value_numeric == 0.5


async def test_other_workspace_sees_nothing(uow, session_factory, workspace_id):
    w = await _world(uow, workspace_id)
    other = uuid.uuid4()
    reader = SQLAlchemyVisualizationDatasetReader(session_factory)

    assert await reader.fetch_well_values(other, [w["run"]]) == []
    assert await reader.runs_by_ids(other, [w["run"]]) == []
    assert await reader.runs_for_protocol(other, w["p"]) is None
    assert await reader.readout_definitions(other, [w["p"]]) == []
    assert await reader.count_wells_rows(other, [w["run"]]) == {}


async def test_well_of_another_runs_plate_is_not_joined(uow, session_factory, workspace_id):
    """A readout pointing at a well outside its own run (here: another workspace's) reads
    as well-less: none of that well's plate, barcode, label or dose comes through."""
    w = await _world(uow, workspace_id)
    other = uuid.uuid4()
    async with uow:
        s = uow.session
        o = await seed.org(s, other)
        mol = await seed.molecule(s, other, o, "foreign")
        p = await seed.protocol(s, other)
        run = await seed.run(s, other, p, date(2026, 11, 12))
        plate = await seed.plate(s, run, 7, barcode="SECRET-BC")
        foreign = await seed.well(s, plate, "H", 12, dose=99.0)
        await s.execute(
            sa.text("UPDATE wells SET label = 'secret' WHERE id = :id"), {"id": foreign}
        )
        await seed.readout(s, workspace_id, w["run"], w["rd"], mol, 1.0, well_id=foreign)
        await uow.commit()
    reader = SQLAlchemyVisualizationDatasetReader(session_factory)

    rows = await reader.fetch_well_values(workspace_id, [w["run"]])

    planted = next(r for r in rows if r.value_numeric == 1.0)
    assert planted.well_id is None and planted.plate_id is None
    assert (planted.plate_number, planted.plate_barcode) == (None, None)
    assert (planted.well_row, planted.well_label, planted.dose) == (None, None, None)
    assert {r.plate_barcode for r in rows} <= {"BC-1", None}


async def test_count_counts_each_well_once_and_wellless_keys(uow, session_factory, workspace_id):
    w = await _world(uow, workspace_id)
    reader = SQLAlchemyVisualizationDatasetReader(session_factory)

    # B03 (two layers → one row) + A01 + one well-less (molecule, batch) key
    assert await reader.count_wells_rows(workspace_id, [w["run"]]) == {w["run"]: 3}


async def test_runs_and_readout_definitions(uow, session_factory, workspace_id):
    w = await _world(uow, workspace_id)
    reader = SQLAlchemyVisualizationDatasetReader(session_factory)

    runs = await reader.runs_for_protocol(workspace_id, w["p"])
    assert runs is not None and [r.id for r in runs] == [w["run"]]
    assert runs[0].status == "approved" and runs[0].run_date == date(2026, 11, 12)
    assert runs[0].operator_id == seed.USER
    defs = await reader.readout_definitions(workspace_id, [w["p"]])
    assert [(d.id, d.name, d.unit) for d in defs] == [(w["rd"], "Signal", "AU")]
    assert await reader.runs_for_protocol(workspace_id, uuid.uuid4()) is None


async def _dr_world(uow, ws: uuid.UUID) -> dict[str, uuid.UUID]:
    """A dose-response readout with one fitted curve on a batch, in workspace ``ws``."""
    async with uow:
        s = uow.session
        o = await seed.org(s, ws)
        mol = await seed.molecule(s, ws, o, "m1", **seed.descriptors(300.0))
        batch = await seed.batch(s, ws, mol, "B-07")
        p = await seed.protocol(s, ws)
        rd = await seed.readout_def(s, p, name="IC50", data_type="dose_response")
        run = await seed.run(s, ws, p, date(2026, 11, 12), status="approved")
        cid = await seed.curve(
            s, ws, p, run, mol, rd, fitted_value=1.5, r_squared=0.97, batch_id=batch, max_dose=30.0
        )
        await s.execute(
            sa.text(
                "UPDATE dose_response_curves SET confidence_interval_low = 1.1, "
                "confidence_interval_high = 2.2 WHERE id = :id"
            ),
            {"id": cid},
        )
        await uow.commit()
    return {"p": p, "rd": rd, "run": run, "mol": mol, "batch": batch, "curve": cid}


async def test_curves_carry_the_fit_for_the_workspace_runs(uow, session_factory, workspace_id):
    w = await _dr_world(uow, workspace_id)
    other = await _dr_world(uow, uuid.uuid4())
    reader = SQLAlchemyVisualizationDatasetReader(session_factory)

    curves = await reader.fetch_curves(workspace_id, [w["run"], other["run"]])

    assert [c.id for c in curves] == [w["curve"]]
    c = curves[0]
    assert (c.run_id, c.molecule_id, c.batch_id) == (w["run"], w["mol"], w["batch"])
    assert c.readout_definition_id == w["rd"] and c.curve_type == "ic50"
    assert (c.fitted_value, c.top, c.bottom, c.hill_slope) == (1.5, 100.0, 0.0, 1.0)
    assert c.r_squared == 0.97 and c.curve_class == "full" and c.num_points == 3
    assert (c.confidence_interval_low, c.confidence_interval_high) == (1.1, 2.2)
    assert c.raw_data == [{"concentration": 30.0, "response": 50.0}]
    assert c.intercept_values is None  # a curve fitted before intercepts were stored


async def test_curve_on_another_workspaces_run_is_not_read(uow, session_factory, workspace_id):
    """A curve row stamped with this workspace but pointing at a foreign run stays out."""
    w = await _dr_world(uow, workspace_id)
    other = await _dr_world(uow, uuid.uuid4())
    async with uow:
        s = uow.session
        await seed.curve(s, workspace_id, other["p"], other["run"], w["mol"], other["rd"])
        await uow.commit()
    reader = SQLAlchemyVisualizationDatasetReader(session_factory)

    assert await reader.fetch_curves(workspace_id, [other["run"]]) == []


async def test_compound_info_and_batch_numbers_are_workspace_scoped(
    uow, session_factory, workspace_id
):
    w = await _dr_world(uow, workspace_id)
    other = await _dr_world(uow, uuid.uuid4())
    reader = SQLAlchemyVisualizationDatasetReader(session_factory)

    info = await reader.compound_info(workspace_id, [w["mol"], other["mol"]])

    assert list(info) == [w["mol"]]
    m = info[w["mol"]]
    assert m.registration_number.startswith("CV-") and m.smiles == "CCO"
    assert (m.molecular_weight, m.logp, m.tpsa) == (300.0, 1.0, 20.0)
    assert (m.hbd, m.hba, m.rotatable_bonds, m.aromatic_rings) == (1, 2, 3, 1)
    assert await reader.batch_numbers(workspace_id, [w["batch"], other["batch"]]) == {
        w["batch"]: "B-07"
    }


async def test_readout_definitions_carry_dose_unit_curve_type_and_melt_measure(
    uow, session_factory, workspace_id
):
    w = await _dr_world(uow, workspace_id)
    async with uow:
        s = uow.session
        tm = await seed.readout_def(s, w["p"], name="Tm", unit="C", aggregation="median")
        await s.execute(
            sa.text("UPDATE readout_definitions SET melt_config = :c WHERE id = :id"),
            {"c": '{"measure": "tm"}', "id": tm},
        )
        await uow.commit()
    reader = SQLAlchemyVisualizationDatasetReader(session_factory)

    defs = {d.id: d for d in await reader.readout_definitions(workspace_id, [w["p"]])}

    ic50, melt = defs[w["rd"]], defs[tm]
    assert (ic50.dose_unit, ic50.curve_type, ic50.melt_measure) == ("uM", "ic50", None)
    assert (melt.dose_unit, melt.curve_type, melt.melt_measure) == ("uM", None, "tm")
    assert melt.aggregation == "median"
    assert ic50.primary_intercept == seed.DR_CONFIG["intercepts"][0]
    assert melt.primary_intercept is None


async def test_empty_ids_read_nothing_without_a_query():
    reader = SQLAlchemyVisualizationDatasetReader(None)  # type: ignore[arg-type]

    assert await reader.fetch_curves(uuid.uuid4(), []) == []
    assert await reader.compound_info(uuid.uuid4(), []) == {}
    assert await reader.batch_numbers(uuid.uuid4(), []) == {}
