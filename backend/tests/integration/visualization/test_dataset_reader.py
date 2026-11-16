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


async def _batch(s, ws: uuid.UUID, molecule_id: uuid.UUID, number: str) -> uuid.UUID:
    bid = uuid.uuid4()
    await s.execute(
        sa.text(
            "INSERT INTO batches (id, workspace_id, molecule_id, batch_number, amount_value, "
            "amount_unit, source, chemist, version) "
            "VALUES (:id, :ws, :m, :n, 1, 'mg', 'synthesized', :chemist, 1)"
        ),
        {"id": bid, "ws": ws, "m": molecule_id, "n": number, "chemist": seed.USER},
    )
    return bid


async def _world(uow, ws: uuid.UUID) -> dict[str, uuid.UUID]:
    """Protocol with one run: plate 1 has B03 (sample, two layers) and A01 (neg control);
    plus one well-less summary row."""
    async with uow:
        s = uow.session
        o = await seed.org(s, ws)
        mol = await seed.molecule(s, ws, o, "m1")
        batch = await _batch(s, ws, mol, "B-01")
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
