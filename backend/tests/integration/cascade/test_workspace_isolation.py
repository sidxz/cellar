"""Regression test: cascade engine must not leak cross-workspace references.

Scenario
--------
- Workspace A has Protocol PA (no runs).
- Workspace B has Protocol PB with Run RB.

When querying find_inbound_references scoped to workspace A:

1. PA (workspace A, no runs) → empty list.
2. PB (workspace B, has a run) queried *with workspace_id = workspace_A* → empty list,
   because RB belongs to workspace B, not workspace A.

The second assertion is the critical safety property: even if an admin in
workspace A happens to know the UUID of a row in workspace B, they cannot
enumerate that row's children through the cascade engine.
"""
from __future__ import annotations

import uuid
from datetime import date

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from cellar.infrastructure.cascade.inbound_refs import find_inbound_references


# ---------------------------------------------------------------------------
# Stable workspace IDs for this test module
# ---------------------------------------------------------------------------

WORKSPACE_A_ID = uuid.UUID("aaaaaaaa-0000-0000-0000-aaaaaaaaaaaa")
WORKSPACE_B_ID = uuid.UUID("bbbbbbbb-0000-0000-0000-bbbbbbbbbbbb")
USER_ID = uuid.UUID("cccccccc-0000-0000-0000-000000000001")


# ---------------------------------------------------------------------------
# Raw SQL helpers (same pattern as the rest of this test suite)
# ---------------------------------------------------------------------------


async def _insert_org(
    session: AsyncSession, org_id: uuid.UUID, workspace_id: uuid.UUID
) -> None:
    await session.execute(
        sa.text(
            "INSERT INTO organizations "
            "(id, workspace_id, name, org_type, is_active, version) "
            "VALUES (:id, :ws, 'Iso Test Org', 'internal', true, 1) "
            "ON CONFLICT DO NOTHING"
        ),
        {"id": org_id, "ws": workspace_id},
    )


async def _insert_protocol(
    session: AsyncSession,
    protocol_id: uuid.UUID,
    workspace_id: uuid.UUID,
    *,
    name: str,
) -> None:
    await session.execute(
        sa.text(
            "INSERT INTO protocols "
            "(id, workspace_id, name, protocol_type, status, "
            "is_locked, dose_unit, pos_control_signal, version, protocol_version, created_by) "
            "VALUES (:id, :ws, :name, 'biochemical', 'active', "
            "false, 'uM', 'high', 1, 1, :user)"
        ),
        {
            "id": protocol_id,
            "ws": workspace_id,
            "name": name,
            "user": USER_ID,
        },
    )


async def _insert_run(
    session: AsyncSession,
    run_id: uuid.UUID,
    protocol_id: uuid.UUID,
    workspace_id: uuid.UUID,
) -> None:
    await session.execute(
        sa.text(
            "INSERT INTO runs "
            "(id, workspace_id, protocol_id, run_date, operator, "
            "status, is_locked, version, notes) "
            "VALUES (:id, :ws, :proto, :run_date, :user, "
            "'draft', false, 1, :notes)"
        ),
        {
            "id": run_id,
            "ws": workspace_id,
            "proto": protocol_id,
            "run_date": date.today(),
            "user": USER_ID,
            "notes": "IsolationRun",
        },
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_protocol_in_workspace_a_has_no_refs(db_session: AsyncSession) -> None:
    """PA lives in workspace A and has no runs — refs scoped to A should be empty."""
    org_a_id = uuid.uuid4()
    pa_id = uuid.uuid4()

    await _insert_org(db_session, org_a_id, WORKSPACE_A_ID)
    await _insert_protocol(db_session, pa_id, WORKSPACE_A_ID, name="PA-IsoTest")

    refs = await find_inbound_references(
        db_session,
        parent_table="protocols",
        parent_id=pa_id,
        workspace_id=WORKSPACE_A_ID,
    )

    assert refs == [], f"expected no refs for PA in workspace A, got: {refs}"


@pytest.mark.asyncio
async def test_cross_workspace_refs_invisible(db_session: AsyncSession) -> None:
    """Critical isolation property: querying PB's refs with workspace_A_id returns empty.

    PB lives in workspace B and has one run (RB) in workspace B.  An admin
    operating under workspace A should see zero references — the run belongs
    to workspace B and must not be visible across the boundary.
    """
    org_b_id = uuid.uuid4()
    pb_id = uuid.uuid4()
    rb_id = uuid.uuid4()

    await _insert_org(db_session, org_b_id, WORKSPACE_B_ID)
    await _insert_protocol(db_session, pb_id, WORKSPACE_B_ID, name="PB-IsoTest")
    await _insert_run(db_session, rb_id, pb_id, WORKSPACE_B_ID)

    # Sanity check: querying with the CORRECT workspace sees the run.
    refs_correct_ws = await find_inbound_references(
        db_session,
        parent_table="protocols",
        parent_id=pb_id,
        workspace_id=WORKSPACE_B_ID,
    )
    run_ref = next((r for r in refs_correct_ws if r.table == "runs"), None)
    assert run_ref is not None and run_ref.count == 1, (
        "sanity check failed: RB should be visible when queried from workspace B"
    )

    # The real test: the WRONG workspace sees nothing.
    refs_wrong_ws = await find_inbound_references(
        db_session,
        parent_table="protocols",
        parent_id=pb_id,
        workspace_id=WORKSPACE_A_ID,
    )
    run_tables = [r.table for r in refs_wrong_ws if r.table == "runs"]
    assert run_tables == [], (
        f"isolation breach: workspace A can see runs belonging to workspace B: "
        f"{refs_wrong_ws}"
    )
