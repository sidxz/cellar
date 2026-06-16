"""EXPLAIN evidence: the /rows query rides the composite PKs (no new index needed).

With enable_seqscan disabled, Postgres falls back to an index scan iff one is
*usable* for the query shape — so this proves index usability on a tiny seed. The
SQL mirrors SQLAlchemyDecompositionRowReader.fetch_rows; keep them in sync.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import text

from cellar.domain.sar_analysis.rgroup_decomposition_run import RGroupDecompositionRun
from cellar.domain.sar_analysis.rgroup_types import RGroupAssignment
from cellar.domain.sar_analysis.sar_activity_projection import SarActivityProjection
from cellar.infrastructure.persistence.sqlalchemy.sar_analysis.rgroup_decomposition_run_repository import (  # noqa: E501
    SQLAlchemyRGroupDecompositionRunRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.sar_analysis.sar_activity_projection_repository import (  # noqa: E501
    SQLAlchemySarActivityProjectionRepository,
)
from cellar.domain.sar_analysis.activity_projection_types import ActivityScalar

_NOW = datetime(2026, 6, 16, tzinfo=UTC)

_ROWS_SQL = """
SELECT rga.molecule_id, m.smiles, m.registration_number, m.name, rga.rgroups,
       m.molecular_weight, m.logp, m.tpsa,
       sav.scalar AS activity, sav.snapshot AS activity_snapshot
FROM rgroup_assignments rga
JOIN rgroup_decomposition_runs r ON r.id = rga.run_id
JOIN molecules m ON m.id = rga.molecule_id
LEFT JOIN sar_activity_values sav
       ON sav.projection_id = :pid AND sav.molecule_id = rga.molecule_id
WHERE rga.run_id = :rid AND r.workspace_id = :ws AND m.workspace_id = :ws
      AND m.merged_into_id IS NULL AND m.molecular_weight > :mw
ORDER BY m.registration_number ASC NULLS LAST, rga.molecule_id
LIMIT 100
"""


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


async def _seed_molecule(uow, ws, org, *, reg, smiles, mw):
    mol_id = uuid.uuid4()
    await uow.session.execute(
        text(
            "INSERT INTO molecules (id, workspace_id, registration_number, name, molecule_type, "
            "smiles, molecular_weight, version, originating_org_id) "
            "VALUES (:id, :ws, :r, :r, 'small_molecule', :smi, :mw, 1, :org)"
        ),
        {"id": mol_id, "ws": ws, "r": reg, "smi": smiles, "mw": mw, "org": org},
    )
    return mol_id


@pytest.mark.asyncio
async def test_rows_query_uses_pk_indexes(uow, capsys):
    ws = uuid.uuid4()
    async with uow:
        org = await _seed_org(uow, ws)
        a = await _seed_molecule(uow, ws, org, reg="CV-A", smiles="Fc1ccccc1", mw=120.0)
        b = await _seed_molecule(uow, ws, org, reg="CV-B", smiles="Clc1ccccc1", mw=130.0)
        run = (
            RGroupDecompositionRun.create(
                workspace_id=ws,
                requested_by=uuid.uuid4(),
                membership_hash="m",
                core_smiles="c1ccccc1",
                core_hash="ch",
                now=_NOW,
            )
            .mark_running(_NOW)
            .mark_ready(
                rgroup_labels=["R1"],
                matched_count=2,
                unmatched_count=0,
                total_count=2,
                now=_NOW,
            )
        )
        run_repo = SQLAlchemyRGroupDecompositionRunRepository(uow)
        await run_repo.save(run)
        await run_repo.write_assignments(
            run.id,
            [
                RGroupAssignment(molecule_id=a, rgroups={"R1": "F"}),
                RGroupAssignment(molecule_id=b, rgroups={"R1": "Cl"}),
            ],
        )

        # Seed projection via domain + repository (matches the real schema exactly)
        proj = (
            SarActivityProjection.create(
                workspace_id=ws,
                requested_by=uuid.uuid4(),
                membership_hash="m",
                channel_hash="ch",
                channel_spec={"column": "drc:x"},
                now=_NOW,
            )
            .mark_running(_NOW)
            .mark_ready(value_count=1, now=_NOW)
        )
        proj_repo = SQLAlchemySarActivityProjectionRepository(uow)
        await proj_repo.save(proj)
        await proj_repo.write_values(
            proj.id,
            [
                ActivityScalar(
                    molecule_id=a,
                    scalar=0.5,
                    unit="uM",
                    qualifier=None,
                    source="dose_response",
                    snapshot={},
                )
            ],
        )

        await uow.session.execute(text("SET LOCAL enable_seqscan = off"))
        plan_rows = (
            await uow.session.execute(
                text("EXPLAIN (FORMAT TEXT) " + _ROWS_SQL),
                {"pid": proj.id, "rid": run.id, "ws": ws, "mw": 0.0},
            )
        ).scalars().all()
    plan = "\n".join(plan_rows)
    print("\n=== EXPLAIN /rows (enable_seqscan=off) ===\n" + plan)

    assert "Seq Scan on rgroup_assignments" not in plan
    assert "Seq Scan on sar_activity_values" not in plan
    assert "Index" in plan
