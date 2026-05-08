"""Integration tests: inbound FK introspection utility.

Uses raw SQL inserts (same pattern as the rest of this project's
integration tests) to avoid dependency on domain factories.

RunModel has no ``name`` column — ``notes`` is used as the human
label for runs in TABLE_LABELS.
"""
from __future__ import annotations

import uuid
from datetime import date

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from chem_vault.infrastructure.cascade.inbound_refs import find_inbound_references


# ---------------------------------------------------------------------------
# Raw SQL helpers
# ---------------------------------------------------------------------------

WORKSPACE_ID = uuid.UUID("aaaaaaaa-0000-0000-0000-000000000001")
USER_ID = uuid.UUID("bbbbbbbb-0000-0000-0000-000000000001")


async def _insert_org(session: AsyncSession, org_id: uuid.UUID) -> None:
    await session.execute(
        sa.text(
            "INSERT INTO organizations "
            "(id, workspace_id, name, org_type, is_active, version) "
            "VALUES (:id, :ws, 'Test Org', 'internal', true, 1) "
            "ON CONFLICT DO NOTHING"
        ),
        {"id": org_id, "ws": WORKSPACE_ID},
    )


async def _insert_protocol(
    session: AsyncSession,
    protocol_id: uuid.UUID,
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
            "ws": WORKSPACE_ID,
            "name": f"Protocol-{str(protocol_id)[:8]}",
            "user": USER_ID,
        },
    )


async def _insert_run(
    session: AsyncSession,
    run_id: uuid.UUID,
    protocol_id: uuid.UUID,
    *,
    notes: str | None = None,
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
            "ws": WORKSPACE_ID,
            "proto": protocol_id,
            "run_date": date.today(),
            "user": USER_ID,
            "notes": notes,
        },
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_protocol_with_no_runs_has_no_blockers(db_session: AsyncSession) -> None:
    """A freshly inserted protocol with no downstream records returns no refs."""
    org_id = uuid.uuid4()
    protocol_id = uuid.uuid4()

    await _insert_org(db_session, org_id)
    await _insert_protocol(db_session, protocol_id)

    refs = await find_inbound_references(
        db_session,
        parent_table="protocols",
        parent_id=protocol_id,
    )

    assert refs == []


@pytest.mark.asyncio
async def test_protocol_with_runs_returns_run_blocker(db_session: AsyncSession) -> None:
    """Two runs linked to a protocol appear as a single run blocker with count=2."""
    org_id = uuid.uuid4()
    protocol_id = uuid.uuid4()
    run_a_id = uuid.uuid4()
    run_b_id = uuid.uuid4()

    await _insert_org(db_session, org_id)
    await _insert_protocol(db_session, protocol_id)
    await _insert_run(db_session, run_a_id, protocol_id, notes="R-A")
    await _insert_run(db_session, run_b_id, protocol_id, notes="R-B")

    refs = await find_inbound_references(
        db_session,
        parent_table="protocols",
        parent_id=protocol_id,
    )

    run_ref = next((r for r in refs if r.table == "runs"), None)
    assert run_ref is not None, f"expected 'runs' blocker, got: {[r.table for r in refs]}"
    assert run_ref.count == 2
    assert run_ref.entity_type == "run"
    labels = {s["label"] for s in run_ref.samples}
    assert {"R-A", "R-B"}.issubset(labels)
    assert run_ref.truncated is False


@pytest.mark.asyncio
async def test_truncated_when_more_than_sample_limit(db_session: AsyncSession) -> None:
    """When count > sample_limit, truncated=True and only sample_limit samples returned."""
    org_id = uuid.uuid4()
    protocol_id = uuid.uuid4()

    await _insert_org(db_session, org_id)
    await _insert_protocol(db_session, protocol_id)

    for i in range(7):
        await _insert_run(db_session, uuid.uuid4(), protocol_id, notes=f"R-{i}")

    refs = await find_inbound_references(
        db_session,
        parent_table="protocols",
        parent_id=protocol_id,
        sample_limit=5,
    )

    run_ref = next((r for r in refs if r.table == "runs"), None)
    assert run_ref is not None
    assert run_ref.count == 7
    assert len(run_ref.samples) == 5
    assert run_ref.truncated is True
