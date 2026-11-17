"""A compound is tested by a run through its sample wells or well-less rows only: one that sits
in a run only as a control or reference is not counted, covered or matched as tested."""

from __future__ import annotations

import uuid
from datetime import date

import pytest

from cellar.domain.research_organization.collection import Collection
from cellar.infrastructure.persistence.sqlalchemy.chemical_registration.molecule_reader import (
    SQLAlchemyMoleculeReader,
)
from cellar.infrastructure.persistence.sqlalchemy.research_organization.collection_repository import (  # noqa: E501
    SQLAlchemyCollectionRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.screening_assay.coverage_query import (
    SQLAlchemyCollectionCoverageQuery,
)
from cellar.infrastructure.persistence.sqlalchemy.screening_assay.protocol_stats_reader import (
    SQLAlchemyProtocolStatsReader,
)
from cellar.infrastructure.persistence.sqlalchemy.screening_assay.readout_data_repository import (
    SQLAlchemyReadoutDataRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.screening_assay.run_repository import (
    SQLAlchemyRunRepository,
)
from tests.integration import _screening_seed as seed

pytestmark = pytest.mark.asyncio


@pytest.fixture
async def world(uow, workspace_id):
    """One run: rifampicin on a sample well and a positive-control well; `summary` on a
    well-less row; `control_only` on a reference well only. A collection holds all three
    and is attached to the run."""
    async with uow:
        s = uow.session
        o = await seed.org(s, workspace_id)
        rif = await seed.molecule(s, workspace_id, o, "rif", **seed.descriptors(300.0))
        summary = await seed.molecule(s, workspace_id, o, "summary", **seed.descriptors(300.0))
        control_only = await seed.molecule(s, workspace_id, o, "ref", **seed.descriptors(300.0))
        p = await seed.protocol(s, workspace_id)
        rd = await seed.readout_def(s, p, name="Growth", unit="%")
        run = await seed.run(s, workspace_id, p, date(2026, 1, 1), status="completed")
        plate = await seed.plate(s, run, 1)
        for col, (role, mol) in enumerate(
            [("sample", rif), ("positive_control", rif), ("reference", control_only)], start=1
        ):
            w = await seed.well(s, plate, "A", col, well_type=role)
            await seed.readout(s, workspace_id, run, rd, mol, 50.0, well_id=w)
        await seed.readout(s, workspace_id, run, rd, summary, 50.0, wellless=True)
        coll = uuid.uuid4()
        await SQLAlchemyCollectionRepository(uow).save(
            Collection(id=coll, workspace_id=workspace_id, name="Library", created_by=seed.USER)
        )
        await uow.commit()
    async with uow:
        await SQLAlchemyCollectionRepository(uow).add_molecules(
            workspace_id, coll, [rif, summary, control_only]
        )
        await SQLAlchemyRunRepository(uow).add_collection(workspace_id, run, coll)
        await uow.commit()
    return {"p": p, "run": run, "coll": coll, "tested": {rif, summary}, "ctrl": control_only}


async def test_protocol_stats_count_tested_compounds_only(session_factory, workspace_id, world):
    stats = await SQLAlchemyProtocolStatsReader(session_factory).get_stats_data(
        workspace_id, world["p"]
    )
    assert stats.compound_count == 2
    assert stats.latest_run is not None
    assert stats.latest_run.compound_count == 2


async def test_run_molecule_counts_count_tested_compounds_only(uow, workspace_id, world):
    async with uow:
        counts = await SQLAlchemyReadoutDataRepository(uow).get_molecule_counts(
            workspace_id, [world["run"]]
        )
    assert counts == {world["run"]: 2}


async def test_collection_coverage_covers_tested_compounds_only(uow, workspace_id, world):
    q = SQLAlchemyCollectionCoverageQuery(uow)
    run, coll = world["run"], world["coll"]
    async with uow:
        [per_run] = (await q.run_coverage(workspace_id, [run]))[run]
        [per_protocol] = await q.protocol_coverage(workspace_id, world["p"])
        [per_runs] = await q.runs_coverage(workspace_id, [coll], [run])
        gaps = [
            await q.run_gap(workspace_id, run, coll),
            await q.protocol_gap(workspace_id, world["p"], coll),
            await q.runs_gap(workspace_id, coll, [run]),
        ]
    assert [c.covered for c in (per_run, per_protocol, per_runs)] == [2, 2, 2]
    assert gaps == [[world["ctrl"]]] * 3


async def test_a_run_date_search_matches_tested_compounds_only(
    session_factory, workspace_id, world
):
    query = {"logic": "and", "criteria": [{"type": "run_date", "date_from": "2026-01-01"}]}
    found = await SQLAlchemyMoleculeReader(session_factory).search_by_query(workspace_id, query)
    assert {m.id for m in found} == world["tested"]
