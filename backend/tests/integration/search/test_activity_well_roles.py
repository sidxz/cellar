"""A compound matches an activity search by its sample wells and well-less rows only."""

from __future__ import annotations

import uuid
from datetime import date

import pytest

from cellar.infrastructure.persistence.sqlalchemy.chemical_registration.molecule_reader import (
    SQLAlchemyMoleculeReader,
)
from tests.integration import _screening_seed as seed

pytestmark = pytest.mark.asyncio


async def _matches(session_factory, workspace_id, criterion) -> set[uuid.UUID]:
    reader = SQLAlchemyMoleculeReader(session_factory)
    query = {"logic": "and", "criteria": [criterion]}
    return {m.id for m in await reader.search_by_query(workspace_id, query)}


@pytest.fixture
async def world(uow, workspace_id):
    """Rifampicin: a 40 % sample well and a 100 % positive-control well. `control_only`:
    one reference well at 95 %."""
    async with uow:
        s = uow.session
        o = await seed.org(s, workspace_id)
        rif = await seed.molecule(s, workspace_id, o, "rif", **seed.descriptors(800.0))
        control_only = await seed.molecule(s, workspace_id, o, "ref", **seed.descriptors(300.0))
        p = await seed.protocol(s, workspace_id)
        rd = await seed.readout_def(s, p, name="Growth", unit="%")
        run = await seed.run(s, workspace_id, p, date(2026, 1, 1))
        plate = await seed.plate(s, run, 1)
        for col, (role, mol, value) in enumerate(
            [
                ("sample", rif, 40.0),
                ("positive_control", rif, 100.0),
                ("reference", control_only, 95.0),
            ],
            start=1,
        ):
            w = await seed.well(s, plate, "A", col, well_type=role)
            await seed.readout(s, workspace_id, run, rd, mol, value, well_id=w)
        await uow.commit()
    return {"rif": rif, "control_only": control_only, "p": p, "rd": rd}


async def test_a_readout_cutoff_ignores_control_and_reference_wells(
    session_factory, workspace_id, world
):
    where = {"source": "readout_data", "readout_definition_id": str(world["rd"])}
    above_90 = {**where, "operator": "gt", "value": 90}
    below_50 = {**where, "operator": "lt", "value": 50}

    def activity(cond, **extra):
        return {"type": "activity", "protocol_id": str(world["p"]), "where": [cond], **extra}

    assert await _matches(session_factory, workspace_id, activity(above_90)) == set()
    every_run = activity(below_50, run_scope={"mode": "all"})
    assert await _matches(session_factory, workspace_id, every_run) == {world["rif"]}


async def test_presence_and_any_protocol_readouts_ignore_control_wells(
    session_factory, workspace_id, world
):
    presence = {"type": "activity", "protocol_id": str(world["p"])}
    by_name = {
        "type": "activity",
        "where": [
            {"source": "readout_data", "readout_name": "Growth", "unit": "%", "operator": "gt",
             "value": 90}
        ],
    }  # fmt: skip

    assert await _matches(session_factory, workspace_id, presence) == {world["rif"]}
    assert await _matches(session_factory, workspace_id, by_name) == set()
