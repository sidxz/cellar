"""Integration tests for SQLAlchemyDecompositionRowReader (assignment ⋈ molecule)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import text

from cellar.application.sar_analysis.decomposition_rows import DecompositionRowSort
from cellar.domain.sar_analysis.rgroup_decomposition_run import RGroupDecompositionRun
from cellar.domain.sar_analysis.rgroup_types import RGroupAssignment
from cellar.infrastructure.persistence.sqlalchemy.sar_analysis.decomposition_row_reader import (
    SQLAlchemyDecompositionRowReader,
)
from cellar.infrastructure.persistence.sqlalchemy.sar_analysis.rgroup_decomposition_run_repository import (  # noqa: E501
    SQLAlchemyRGroupDecompositionRunRepository,
)

_NOW = datetime(2026, 6, 15, tzinfo=UTC)


async def _seed_org(uow, ws):
    org_id = uuid.uuid4()
    await uow.session.execute(
        text(
            "INSERT INTO organizations (id, workspace_id, name, org_type, is_active, version) "
            "VALUES (:id, :ws, :n, 'internal', true, 1)"
        ),
        {"id": org_id, "ws": ws, "n": f"org-{org_id.hex[:6]}"},
    )
    return org_id


async def _seed_molecule(uow, ws, org, *, reg, smiles, mw=None, logp=None, tpsa=None, merged=None):
    mol_id = uuid.uuid4()
    await uow.session.execute(
        text(
            "INSERT INTO molecules (id, workspace_id, registration_number, name, molecule_type, "
            "smiles, molecular_weight, logp, tpsa, version, originating_org_id, merged_into_id) "
            "VALUES (:id, :ws, :r, :r, 'small_molecule', :smi, :mw, :logp, :tpsa, 1, :org, :merged)"
        ),
        {"id": mol_id, "ws": ws, "r": reg, "smi": smiles, "mw": mw, "logp": logp,
         "tpsa": tpsa, "org": org, "merged": merged},
    )
    return mol_id


async def _seed_ready_run(uow, ws):
    run = RGroupDecompositionRun.create(
        workspace_id=ws, requested_by=uuid.uuid4(), membership_hash="m",
        core_smiles="c1ccccc1", core_hash="ch", now=_NOW,
    ).mark_running(_NOW).mark_ready(
        rgroup_labels=["R1"], matched_count=0, unmatched_count=0, total_count=0, now=_NOW
    )
    repo = SQLAlchemyRGroupDecompositionRunRepository(uow)
    await repo.save(run)
    return run


@pytest.mark.asyncio
async def test_fetch_rows_joins_molecule_fields(uow):
    ws = uuid.uuid4()
    async with uow:
        org = await _seed_org(uow, ws)
        m = await _seed_molecule(uow, ws, org, reg="CV-1", smiles="Fc1ccccc1", mw=96.1, logp=1.8, tpsa=0.0)
        run = await _seed_ready_run(uow, ws)
        repo = SQLAlchemyRGroupDecompositionRunRepository(uow)
        await repo.write_assignments(run.id, [RGroupAssignment(molecule_id=m, rgroups={"R1": "F"})])
        await uow.commit()

    async with uow:
        reader = SQLAlchemyDecompositionRowReader(uow)
        rows = await reader.fetch_rows(run.id, workspace_id=ws, offset=0, limit=50, sort=[])
        total = await reader.count_rows(run.id, workspace_id=ws)

    assert total == 1
    row = rows[0]
    assert row.molecule_id == m
    assert row.smiles == "Fc1ccccc1"
    assert row.registration_number == "CV-1"
    assert row.rgroups == {"R1": "F"}
    assert row.molecular_weight == pytest.approx(96.1)
    assert row.logp == pytest.approx(1.8)


@pytest.mark.asyncio
async def test_fetch_rows_sorts_by_registration_number(uow):
    ws = uuid.uuid4()
    async with uow:
        org = await _seed_org(uow, ws)
        run = await _seed_ready_run(uow, ws)
        repo = SQLAlchemyRGroupDecompositionRunRepository(uow)
        asg = []
        for reg in ("CV-C", "CV-A", "CV-B"):
            m = await _seed_molecule(uow, ws, org, reg=reg, smiles="Fc1ccccc1")
            asg.append(RGroupAssignment(molecule_id=m, rgroups={"R1": "F"}))
        await repo.write_assignments(run.id, asg)
        await uow.commit()

    async with uow:
        reader = SQLAlchemyDecompositionRowReader(uow)
        asc = await reader.fetch_rows(
            run.id, workspace_id=ws, offset=0, limit=50,
            sort=[DecompositionRowSort(col="registration_number", direction="asc")],
        )
    assert [r.registration_number for r in asc] == ["CV-A", "CV-B", "CV-C"]


@pytest.mark.asyncio
async def test_fetch_rows_sorts_by_rgroup_label(uow):
    ws = uuid.uuid4()
    async with uow:
        org = await _seed_org(uow, ws)
        run = await _seed_ready_run(uow, ws)
        repo = SQLAlchemyRGroupDecompositionRunRepository(uow)
        asg = []
        for reg, r1 in (("CV-1", "Cl"), ("CV-2", "Br"), ("CV-3", "F")):
            m = await _seed_molecule(uow, ws, org, reg=reg, smiles="Fc1ccccc1")
            asg.append(RGroupAssignment(molecule_id=m, rgroups={"R1": r1}))
        await repo.write_assignments(run.id, asg)
        await uow.commit()

    async with uow:
        reader = SQLAlchemyDecompositionRowReader(uow)
        rows = await reader.fetch_rows(
            run.id, workspace_id=ws, offset=0, limit=50,
            sort=[DecompositionRowSort(col="R1", direction="asc")],
        )
    assert [r.rgroups["R1"] for r in rows] == ["Br", "Cl", "F"]


@pytest.mark.asyncio
async def test_fetch_rows_paginates_stably(uow):
    ws = uuid.uuid4()
    async with uow:
        org = await _seed_org(uow, ws)
        run = await _seed_ready_run(uow, ws)
        repo = SQLAlchemyRGroupDecompositionRunRepository(uow)
        asg = []
        for i in range(5):
            m = await _seed_molecule(uow, ws, org, reg=f"CV-{i}", smiles="Fc1ccccc1")
            asg.append(RGroupAssignment(molecule_id=m, rgroups={"R1": "F"}))
        await repo.write_assignments(run.id, asg)
        await uow.commit()

    async with uow:
        reader = SQLAlchemyDecompositionRowReader(uow)
        p1 = await reader.fetch_rows(run.id, workspace_id=ws, offset=0, limit=2, sort=[])
        p2 = await reader.fetch_rows(run.id, workspace_id=ws, offset=2, limit=2, sort=[])
        p3 = await reader.fetch_rows(run.id, workspace_id=ws, offset=4, limit=2, sort=[])
    seen = [r.molecule_id for r in (*p1, *p2, *p3)]
    assert len(seen) == 5 and len(set(seen)) == 5


@pytest.mark.asyncio
async def test_fetch_rows_excludes_merged_and_scopes_workspace(uow):
    ws = uuid.uuid4()
    async with uow:
        org = await _seed_org(uow, ws)
        run = await _seed_ready_run(uow, ws)
        repo = SQLAlchemyRGroupDecompositionRunRepository(uow)
        visible = await _seed_molecule(uow, ws, org, reg="CV-V", smiles="Fc1ccccc1")
        merged = await _seed_molecule(uow, ws, org, reg="CV-M", smiles="CCO", merged=uuid.uuid4())
        await repo.write_assignments(
            run.id,
            [
                RGroupAssignment(molecule_id=visible, rgroups={"R1": "F"}),
                RGroupAssignment(molecule_id=merged, rgroups={"R1": "OH"}),
            ],
        )
        await uow.commit()

    async with uow:
        reader = SQLAlchemyDecompositionRowReader(uow)
        rows = await reader.fetch_rows(run.id, workspace_id=ws, offset=0, limit=50, sort=[])
        total = await reader.count_rows(run.id, workspace_id=ws)
        other = await reader.fetch_rows(run.id, workspace_id=uuid.uuid4(), offset=0, limit=50, sort=[])

    assert {r.molecule_id for r in rows} == {visible}  # merged excluded
    assert total == 1
    assert other == []  # wrong workspace sees nothing
