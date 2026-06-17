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
    )
    run.mark_running(_NOW)
    run.mark_ready(
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


async def _seed_ready_projection(uow, ws):
    from cellar.domain.sar_analysis.sar_activity_projection import SarActivityProjection
    from cellar.infrastructure.persistence.sqlalchemy.sar_analysis.sar_activity_projection_repository import (  # noqa: E501
        SQLAlchemySarActivityProjectionRepository,
    )

    proj = SarActivityProjection.create(
        workspace_id=ws, requested_by=uuid.uuid4(), membership_hash="m",
        channel_hash="ch", channel_spec={"column": "drc:x"}, now=_NOW,
    )
    proj.mark_running(_NOW)
    proj.mark_ready(value_count=0, now=_NOW)
    await SQLAlchemySarActivityProjectionRepository(uow).save(proj)
    return proj


@pytest.mark.asyncio
async def test_fetch_rows_joins_activity_when_projection_given(uow):
    from cellar.domain.sar_analysis.activity_projection_types import ActivityScalar
    from cellar.infrastructure.persistence.sqlalchemy.sar_analysis.sar_activity_projection_repository import (  # noqa: E501
        SQLAlchemySarActivityProjectionRepository,
    )

    ws = uuid.uuid4()
    async with uow:
        org = await _seed_org(uow, ws)
        run = await _seed_ready_run(uow, ws)
        proj = await _seed_ready_projection(uow, ws)
        repo = SQLAlchemyRGroupDecompositionRunRepository(uow)
        with_act = await _seed_molecule(uow, ws, org, reg="CV-ACT", smiles="Fc1ccccc1")
        no_act = await _seed_molecule(uow, ws, org, reg="CV-NONE", smiles="Clc1ccccc1")
        await repo.write_assignments(run.id, [
            RGroupAssignment(molecule_id=with_act, rgroups={"R1": "F"}),
            RGroupAssignment(molecule_id=no_act, rgroups={"R1": "Cl"}),
        ])
        await SQLAlchemySarActivityProjectionRepository(uow).write_values(proj.id, [
            ActivityScalar(molecule_id=with_act, scalar=0.7, unit="uM", qualifier=None,
                           source="dose_response", snapshot={}),
        ])
        await uow.commit()

    async with uow:
        reader = SQLAlchemyDecompositionRowReader(uow)
        rows = await reader.fetch_rows(
            run.id, workspace_id=ws, offset=0, limit=50, sort=[], projection_id=proj.id
        )
    by_reg = {r.registration_number: r for r in rows}
    assert by_reg["CV-ACT"].activity == pytest.approx(0.7)
    assert by_reg["CV-NONE"].activity is None  # sparse LEFT JOIN null


@pytest.mark.asyncio
async def test_fetch_rows_sorts_by_activity(uow):
    from cellar.domain.sar_analysis.activity_projection_types import ActivityScalar
    from cellar.infrastructure.persistence.sqlalchemy.sar_analysis.sar_activity_projection_repository import (  # noqa: E501
        SQLAlchemySarActivityProjectionRepository,
    )

    ws = uuid.uuid4()
    async with uow:
        org = await _seed_org(uow, ws)
        run = await _seed_ready_run(uow, ws)
        proj = await _seed_ready_projection(uow, ws)
        repo = SQLAlchemyRGroupDecompositionRunRepository(uow)
        values = []
        for reg, scalar in (("CV-HI", 9.0), ("CV-LO", 0.2), ("CV-MID", 1.5)):
            m = await _seed_molecule(uow, ws, org, reg=reg, smiles="Fc1ccccc1")
            await repo.write_assignments(run.id, [RGroupAssignment(molecule_id=m, rgroups={"R1": "F"})])
            values.append(ActivityScalar(molecule_id=m, scalar=scalar, unit="uM", qualifier=None,
                                         source="dose_response", snapshot={}))
        await SQLAlchemySarActivityProjectionRepository(uow).write_values(proj.id, values)
        await uow.commit()

    async with uow:
        reader = SQLAlchemyDecompositionRowReader(uow)
        rows = await reader.fetch_rows(
            run.id, workspace_id=ws, offset=0, limit=50,
            sort=[DecompositionRowSort(col="activity", direction="asc")], projection_id=proj.id,
        )
    assert [r.registration_number for r in rows] == ["CV-LO", "CV-MID", "CV-HI"]


@pytest.mark.asyncio
async def test_fetch_rows_activity_is_none_without_projection(uow):
    ws = uuid.uuid4()
    async with uow:
        org = await _seed_org(uow, ws)
        run = await _seed_ready_run(uow, ws)
        repo = SQLAlchemyRGroupDecompositionRunRepository(uow)
        m = await _seed_molecule(uow, ws, org, reg="CV-1", smiles="Fc1ccccc1")
        await repo.write_assignments(run.id, [RGroupAssignment(molecule_id=m, rgroups={"R1": "F"})])
        await uow.commit()

    async with uow:
        reader = SQLAlchemyDecompositionRowReader(uow)
        rows = await reader.fetch_rows(run.id, workspace_id=ws, offset=0, limit=50, sort=[])
    assert rows[0].activity is None  # no projection -> activity absent


@pytest.mark.asyncio
async def test_fetch_rows_numeric_filter_on_physchem(uow):
    ws = uuid.uuid4()
    async with uow:
        org = await _seed_org(uow, ws)
        run = await _seed_ready_run(uow, ws)
        repo = SQLAlchemyRGroupDecompositionRunRepository(uow)
        light = await _seed_molecule(uow, ws, org, reg="CV-LIGHT", smiles="C", mw=100.0)
        heavy = await _seed_molecule(uow, ws, org, reg="CV-HEAVY", smiles="CC", mw=400.0)
        await repo.write_assignments(run.id, [
            RGroupAssignment(molecule_id=light, rgroups={"R1": "F"}),
            RGroupAssignment(molecule_id=heavy, rgroups={"R1": "Cl"}),
        ])
        await uow.commit()
    flt = {"molecular_weight": {"kind": "number", "op": "gte", "value": 300}}
    async with uow:
        reader = SQLAlchemyDecompositionRowReader(uow)
        rows = await reader.fetch_rows(run.id, workspace_id=ws, offset=0, limit=50, sort=[], filter=flt)
        total = await reader.count_rows(run.id, workspace_id=ws, filter=flt)
    assert [r.registration_number for r in rows] == ["CV-HEAVY"]
    assert total == 1  # filtered count


@pytest.mark.asyncio
async def test_fetch_rows_text_filter_on_rgroup(uow):
    ws = uuid.uuid4()
    async with uow:
        org = await _seed_org(uow, ws)
        run = await _seed_ready_run(uow, ws)
        repo = SQLAlchemyRGroupDecompositionRunRepository(uow)
        for reg, r1 in (("CV-1", "Cl"), ("CV-2", "Br"), ("CV-3", "F")):
            m = await _seed_molecule(uow, ws, org, reg=reg, smiles="Fc1ccccc1")
            await repo.write_assignments(run.id, [RGroupAssignment(molecule_id=m, rgroups={"R1": r1})])
        await uow.commit()
    flt = {"R1": {"kind": "text", "op": "eq", "value": "Br"}}
    async with uow:
        reader = SQLAlchemyDecompositionRowReader(uow)
        rows = await reader.fetch_rows(run.id, workspace_id=ws, offset=0, limit=50, sort=[], filter=flt)
    assert [r.rgroups["R1"] for r in rows] == ["Br"]


@pytest.mark.asyncio
async def test_fetch_rows_text_contains_on_registration(uow):
    ws = uuid.uuid4()
    async with uow:
        org = await _seed_org(uow, ws)
        run = await _seed_ready_run(uow, ws)
        repo = SQLAlchemyRGroupDecompositionRunRepository(uow)
        a = await _seed_molecule(uow, ws, org, reg="ABC-1", smiles="Fc1ccccc1")
        b = await _seed_molecule(uow, ws, org, reg="XYZ-2", smiles="Clc1ccccc1")
        await repo.write_assignments(run.id, [
            RGroupAssignment(molecule_id=a, rgroups={"R1": "F"}),
            RGroupAssignment(molecule_id=b, rgroups={"R1": "Cl"}),
        ])
        await uow.commit()
    flt = {"registration_number": {"kind": "text", "op": "contains", "value": "abc"}}  # case-insensitive
    async with uow:
        reader = SQLAlchemyDecompositionRowReader(uow)
        rows = await reader.fetch_rows(run.id, workspace_id=ws, offset=0, limit=50, sort=[], filter=flt)
    assert [r.registration_number for r in rows] == ["ABC-1"]


@pytest.mark.asyncio
async def test_fetch_rows_unknown_filter_clause_is_ignored(uow):
    ws = uuid.uuid4()
    async with uow:
        org = await _seed_org(uow, ws)
        run = await _seed_ready_run(uow, ws)
        repo = SQLAlchemyRGroupDecompositionRunRepository(uow)
        m = await _seed_molecule(uow, ws, org, reg="CV-1", smiles="Fc1ccccc1")
        await repo.write_assignments(run.id, [RGroupAssignment(molecule_id=m, rgroups={"R1": "F"})])
        await uow.commit()
    flt = {"bogus_col": {"kind": "number", "op": "gt", "value": 1}, "R1": {"kind": "text", "op": "weird", "value": "F"}}
    async with uow:
        reader = SQLAlchemyDecompositionRowReader(uow)
        rows = await reader.fetch_rows(run.id, workspace_id=ws, offset=0, limit=50, sort=[], filter=flt)
        total = await reader.count_rows(run.id, workspace_id=ws, filter=flt)
    assert len(rows) == 1 and total == 1  # unknown col + unknown op both skipped (lenient)


@pytest.mark.asyncio
async def test_fetch_rows_returns_snapshot_and_reference(uow):
    from cellar.domain.sar_analysis.activity_projection_types import ActivityScalar
    from cellar.infrastructure.persistence.sqlalchemy.sar_analysis.sar_activity_projection_repository import (  # noqa: E501
        SQLAlchemySarActivityProjectionRepository,
    )

    ws = uuid.uuid4()
    async with uow:
        org = await _seed_org(uow, ws)
        run = await _seed_ready_run(uow, ws)
        proj = await _seed_ready_projection(uow, ws)  # helper added in Part-2 Task 15
        repo = SQLAlchemyRGroupDecompositionRunRepository(uow)
        pr = SQLAlchemySarActivityProjectionRepository(uow)
        potent = await _seed_molecule(uow, ws, org, reg="CV-POTENT", smiles="Fc1ccccc1")
        weak = await _seed_molecule(uow, ws, org, reg="CV-WEAK", smiles="Clc1ccccc1")
        await repo.write_assignments(run.id, [
            RGroupAssignment(molecule_id=potent, rgroups={"R1": "F"}),
            RGroupAssignment(molecule_id=weak, rgroups={"R1": "Cl"}),
        ])
        await pr.write_values(proj.id, [
            ActivityScalar(molecule_id=potent, scalar=0.1, unit="uM", qualifier=None,
                           source="dose_response", snapshot={"value": 0.1, "raw_data": []}),
            ActivityScalar(molecule_id=weak, scalar=5.0, unit="uM", qualifier=None,
                           source="dose_response", snapshot={"value": 5.0}),
        ])
        await uow.commit()
    async with uow:
        reader = SQLAlchemyDecompositionRowReader(uow)
        rows = await reader.fetch_rows(run.id, workspace_id=ws, offset=0, limit=50, sort=[], projection_id=proj.id)
        ref = await reader.activity_reference(run.id, workspace_id=ws, projection_id=proj.id, filter=None)
    by_reg = {r.registration_number: r for r in rows}
    assert by_reg["CV-POTENT"].activity_snapshot == {"value": 0.1, "raw_data": []}
    assert by_reg["CV-WEAK"].activity_snapshot == {"value": 5.0}
    assert ref == pytest.approx(0.1)  # min scalar = most-potent reference


@pytest.mark.asyncio
async def test_activity_reference_none_without_projection(uow):
    ws = uuid.uuid4()
    async with uow:
        org = await _seed_org(uow, ws)
        run = await _seed_ready_run(uow, ws)
        async with uow:
            pass
    async with uow:
        reader = SQLAlchemyDecompositionRowReader(uow)
        ref = await reader.activity_reference(run.id, workspace_id=ws, projection_id=None, filter=None)
    assert ref is None


@pytest.mark.asyncio
async def test_fetch_matched_ids_returns_all_matched(uow):
    ws = uuid.uuid4()
    async with uow:
        org = await _seed_org(uow, ws)
        a = await _seed_molecule(uow, ws, org, reg="CV-A", smiles="Fc1ccccc1")
        b = await _seed_molecule(uow, ws, org, reg="CV-B", smiles="Clc1ccccc1")
        run = await _seed_ready_run(uow, ws)
        repo = SQLAlchemyRGroupDecompositionRunRepository(uow)
        await repo.write_assignments(run.id, [
            RGroupAssignment(molecule_id=a, rgroups={"R1": "F"}),
            RGroupAssignment(molecule_id=b, rgroups={"R1": "Cl"}),
        ])
        await uow.commit()
    async with uow:
        reader = SQLAlchemyDecompositionRowReader(uow)
        ids = await reader.fetch_matched_ids(run.id, workspace_id=ws)
    assert set(ids) == {a, b}


@pytest.mark.asyncio
async def test_fetch_matched_ids_applies_text_filter(uow):
    ws = uuid.uuid4()
    async with uow:
        org = await _seed_org(uow, ws)
        a = await _seed_molecule(uow, ws, org, reg="CV-A", smiles="Fc1ccccc1")
        b = await _seed_molecule(uow, ws, org, reg="CV-B", smiles="Clc1ccccc1")
        run = await _seed_ready_run(uow, ws)
        repo = SQLAlchemyRGroupDecompositionRunRepository(uow)
        await repo.write_assignments(run.id, [
            RGroupAssignment(molecule_id=a, rgroups={"R1": "F"}),
            RGroupAssignment(molecule_id=b, rgroups={"R1": "Cl"}),
        ])
        await uow.commit()
    async with uow:
        reader = SQLAlchemyDecompositionRowReader(uow)
        ids = await reader.fetch_matched_ids(
            run.id, workspace_id=ws, filter={"R1": {"kind": "text", "op": "eq", "value": "Cl"}}
        )
    assert ids == [b]


@pytest.mark.asyncio
async def test_fetch_matched_ids_excludes_merged_and_other_workspace(uow):
    ws = uuid.uuid4()
    other_ws = uuid.uuid4()
    async with uow:
        org = await _seed_org(uow, ws)
        keep = await _seed_molecule(uow, ws, org, reg="CV-A", smiles="Fc1ccccc1")
        merged = await _seed_molecule(
            uow, ws, org, reg="CV-M", smiles="Clc1ccccc1", merged=keep
        )
        run = await _seed_ready_run(uow, ws)
        repo = SQLAlchemyRGroupDecompositionRunRepository(uow)
        await repo.write_assignments(run.id, [
            RGroupAssignment(molecule_id=keep, rgroups={"R1": "F"}),
            RGroupAssignment(molecule_id=merged, rgroups={"R1": "Cl"}),
        ])
        await uow.commit()
    async with uow:
        reader = SQLAlchemyDecompositionRowReader(uow)
        ids = await reader.fetch_matched_ids(run.id, workspace_id=ws)
        wrong_ws = await reader.fetch_matched_ids(run.id, workspace_id=other_ws)
    assert ids == [keep]          # merged-into row excluded
    assert wrong_ws == []         # workspace-scoped
