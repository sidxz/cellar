"""Integration tests for SQLAlchemyActivityHeatmapReader (argmin + top-K cap)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import text

from cellar.domain.sar_analysis.activity_projection_types import ActivityScalar
from cellar.domain.sar_analysis.rgroup_decomposition_run import RGroupDecompositionRun
from cellar.domain.sar_analysis.rgroup_types import RGroupAssignment
from cellar.domain.sar_analysis.sar_activity_projection import SarActivityProjection
from cellar.infrastructure.persistence.sqlalchemy.sar_analysis.activity_heatmap_reader import (
    SQLAlchemyActivityHeatmapReader,
)
from cellar.infrastructure.persistence.sqlalchemy.sar_analysis.rgroup_decomposition_run_repository import (  # noqa: E501
    SQLAlchemyRGroupDecompositionRunRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.sar_analysis.sar_activity_projection_repository import (  # noqa: E501
    SQLAlchemySarActivityProjectionRepository,
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


async def _seed_molecule(uow, ws, org, *, reg):
    mol_id = uuid.uuid4()
    await uow.session.execute(
        text(
            "INSERT INTO molecules (id, workspace_id, registration_number, name, molecule_type, "
            "smiles, version, originating_org_id) "
            "VALUES (:id, :ws, :r, :r, 'small_molecule', 'Fc1ccccc1', 1, :org)"
        ),
        {"id": mol_id, "ws": ws, "r": reg, "org": org},
    )
    return mol_id


async def _ready_run(uow, ws):
    run = RGroupDecompositionRun.create(
        workspace_id=ws, requested_by=uuid.uuid4(), membership_hash="m",
        core_smiles="c1ccccc1", core_hash="ch", now=_NOW,
    )
    run.mark_running(_NOW)
    run.mark_ready(
        rgroup_labels=["R1", "R2"], matched_count=0, unmatched_count=0, total_count=0, now=_NOW
    )
    await SQLAlchemyRGroupDecompositionRunRepository(uow).save(run)
    return run


async def _ready_projection(uow, ws):
    proj = (
        SarActivityProjection.create(
            workspace_id=ws, requested_by=uuid.uuid4(), membership_hash="m",
            channel_hash="ch", channel_spec={"column": "drc:x"}, now=_NOW,
        )
        .mark_running(_NOW)
        .mark_ready(value_count=0, now=_NOW)
    )
    await SQLAlchemySarActivityProjectionRepository(uow).save(proj)
    return proj


@pytest.mark.asyncio
async def test_heatmap_argmin_per_cell(uow):
    ws = uuid.uuid4()
    async with uow:
        org = await _seed_org(uow, ws)
        run = await _ready_run(uow, ws)
        proj = await _ready_projection(uow, ws)
        run_repo = SQLAlchemyRGroupDecompositionRunRepository(uow)
        proj_repo = SQLAlchemySarActivityProjectionRepository(uow)
        # Two molecules in the SAME cell (R1=F, R2=Cl): potent (0.1) and weak (5.0).
        potent = await _seed_molecule(uow, ws, org, reg="CV-POTENT")
        weak = await _seed_molecule(uow, ws, org, reg="CV-WEAK")
        # One molecule in a different cell (R1=Br, R2=Cl).
        other = await _seed_molecule(uow, ws, org, reg="CV-OTHER")
        await run_repo.write_assignments(run.id, [
            RGroupAssignment(molecule_id=potent, rgroups={"R1": "F", "R2": "Cl"}),
            RGroupAssignment(molecule_id=weak, rgroups={"R1": "F", "R2": "Cl"}),
            RGroupAssignment(molecule_id=other, rgroups={"R1": "Br", "R2": "Cl"}),
        ])
        await proj_repo.write_values(proj.id, [
            ActivityScalar(molecule_id=potent, scalar=0.1, unit="uM", qualifier=None,
                           source="dose_response", snapshot={"value": 0.1}),
            ActivityScalar(molecule_id=weak, scalar=5.0, unit="uM", qualifier=None,
                           source="dose_response", snapshot={"value": 5.0}),
            ActivityScalar(molecule_id=other, scalar=2.0, unit="uM", qualifier=None,
                           source="dose_response", snapshot={"value": 2.0}),
        ])
        await uow.commit()

    async with uow:
        reader = SQLAlchemyActivityHeatmapReader(uow)
        res = await reader.fetch_heatmap(
            run.id, workspace_id=ws, projection_id=proj.id, axis_y="R1", axis_x="R2"
        )

    cells = {(c.y, c.x): c for c in res.cells}
    assert ("F", "Cl") in cells and ("Br", "Cl") in cells
    fcl = cells[("F", "Cl")]
    assert fcl.count == 2
    assert fcl.best_scalar == pytest.approx(0.1)  # argmin = the potent one
    assert fcl.best_molecule_id == potent
    assert fcl.best_molecule_label == "CV-POTENT"
    assert fcl.best_snapshot == {"value": 0.1}
    assert res.truncated is False
    assert res.y_total == 2 and res.x_total == 1
    # Server-side reference = min scalar over the whole scored set (0.1, 5.0, 2.0).
    assert res.activity_reference == pytest.approx(0.1)


@pytest.mark.asyncio
async def test_heatmap_keeps_matched_cells_without_activity(uow):
    # A matched (y,x) combo whose molecules have NO activity value still appears
    # as an (uncolored) cell with its full count — the "tested-but-unscreened
    # corner" signal. LEFT join, not INNER; count is over all matched molecules.
    ws = uuid.uuid4()
    async with uow:
        org = await _seed_org(uow, ws)
        run = await _ready_run(uow, ws)
        proj = await _ready_projection(uow, ws)
        run_repo = SQLAlchemyRGroupDecompositionRunRepository(uow)
        proj_repo = SQLAlchemySarActivityProjectionRepository(uow)
        scored = await _seed_molecule(uow, ws, org, reg="CV-SCORED")
        un1 = await _seed_molecule(uow, ws, org, reg="CV-UN1")
        un2 = await _seed_molecule(uow, ws, org, reg="CV-UN2")
        await run_repo.write_assignments(run.id, [
            RGroupAssignment(molecule_id=scored, rgroups={"R1": "F", "R2": "Cl"}),
            RGroupAssignment(molecule_id=un1, rgroups={"R1": "Br", "R2": "Cl"}),
            RGroupAssignment(molecule_id=un2, rgroups={"R1": "Br", "R2": "Cl"}),
        ])
        # Only `scored` has an activity value; the (Br, Cl) corner is unscreened.
        await proj_repo.write_values(proj.id, [
            ActivityScalar(molecule_id=scored, scalar=0.1, unit="uM", qualifier=None,
                           source="dose_response", snapshot={"value": 0.1}),
        ])
        await uow.commit()

    async with uow:
        reader = SQLAlchemyActivityHeatmapReader(uow)
        res = await reader.fetch_heatmap(
            run.id, workspace_id=ws, projection_id=proj.id, axis_y="R1", axis_x="R2"
        )

    cells = {(c.y, c.x): c for c in res.cells}
    assert ("Br", "Cl") in cells  # unscreened corner is NOT dropped
    brcl = cells[("Br", "Cl")]
    assert brcl.count == 2  # both unscreened molecules counted
    assert brcl.best_scalar is None  # no activity → uncolored
    assert brcl.best_snapshot == {}
    assert cells[("F", "Cl")].best_scalar == pytest.approx(0.1)  # scored cell colors
    assert res.activity_reference == pytest.approx(0.1)  # min over the scored set


@pytest.mark.asyncio
async def test_heatmap_caps_axis_to_top_k_by_member_count(uow):
    ws = uuid.uuid4()
    async with uow:
        org = await _seed_org(uow, ws)
        run = await _ready_run(uow, ws)
        proj = await _ready_projection(uow, ws)
        run_repo = SQLAlchemyRGroupDecompositionRunRepository(uow)
        proj_repo = SQLAlchemySarActivityProjectionRepository(uow)
        assignments, values = [], []
        # 4 distinct R1 groups, all with R2=Cl. Group "A" has 3 members; others 1 each.
        plan = [("A", 3), ("B", 1), ("C", 1), ("D", 1)]
        for r1, n in plan:
            for _ in range(n):
                mid = await _seed_molecule(uow, ws, org, reg=f"CV-{r1}-{uuid.uuid4().hex[:4]}")
                assignments.append(RGroupAssignment(molecule_id=mid, rgroups={"R1": r1, "R2": "Cl"}))
                values.append(ActivityScalar(molecule_id=mid, scalar=1.0, unit="uM",
                                             qualifier=None, source="dose_response", snapshot={}))
        await run_repo.write_assignments(run.id, assignments)
        await proj_repo.write_values(proj.id, values)
        await uow.commit()

    async with uow:
        reader = SQLAlchemyActivityHeatmapReader(uow)
        res = await reader.fetch_heatmap(
            run.id, workspace_id=ws, projection_id=proj.id, axis_y="R1", axis_x="R2", top_k=2
        )

    # top_k=2 keeps the two most-populated R1 groups; "A" (3 members) must survive.
    kept = {c.y for c in res.cells}
    assert "A" in kept
    assert len(kept) == 2
    assert res.y_total == 4  # honest total
    assert res.truncated is True


@pytest.mark.asyncio
async def test_heatmap_excludes_molecules_missing_an_axis(uow):
    ws = uuid.uuid4()
    async with uow:
        org = await _seed_org(uow, ws)
        run = await _ready_run(uow, ws)
        proj = await _ready_projection(uow, ws)
        run_repo = SQLAlchemyRGroupDecompositionRunRepository(uow)
        proj_repo = SQLAlchemySarActivityProjectionRepository(uow)
        full = await _seed_molecule(uow, ws, org, reg="CV-FULL")
        partial = await _seed_molecule(uow, ws, org, reg="CV-PARTIAL")
        await run_repo.write_assignments(run.id, [
            RGroupAssignment(molecule_id=full, rgroups={"R1": "F", "R2": "Cl"}),
            RGroupAssignment(molecule_id=partial, rgroups={"R1": "F"}),  # no R2
        ])
        await proj_repo.write_values(proj.id, [
            ActivityScalar(molecule_id=full, scalar=0.1, unit="uM", qualifier=None, source="dose_response", snapshot={}),
            ActivityScalar(molecule_id=partial, scalar=0.2, unit="uM", qualifier=None, source="dose_response", snapshot={}),
        ])
        await uow.commit()

    async with uow:
        reader = SQLAlchemyActivityHeatmapReader(uow)
        res = await reader.fetch_heatmap(run.id, workspace_id=ws, projection_id=proj.id, axis_y="R1", axis_x="R2")

    assert len(res.cells) == 1  # partial (no R2) is not placeable in a 2D cell
    assert res.cells[0].count == 1
