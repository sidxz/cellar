"""Integration tests: CascadeRunner execute engine.

Uses raw SQL inserts (same pattern as test_cascade_runner_preview.py) to avoid
dependency on domain factories.

The cascade rules module must be imported explicitly so the process-global
registry is populated before CascadeRunner.execute() calls get_rules_for_parent().
"""
from __future__ import annotations

import uuid
from datetime import date

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

# Force cascade rules into the registry
import chem_vault.domain.screening_assay.cascade  # noqa: F401
import chem_vault.domain.research_organization.cascade  # noqa: F401

# Force models into Base.metadata
import chem_vault.infrastructure.persistence.sqlalchemy.screening_assay.models  # noqa: F401
import chem_vault.infrastructure.persistence.sqlalchemy.research_organization.models  # noqa: F401

from chem_vault.infrastructure.cascade.cascade_runner import CascadeRunner
from chem_vault.infrastructure.persistence.sqlalchemy.base import Base


# ---------------------------------------------------------------------------
# Stable IDs and raw SQL helpers (mirrors test_cascade_runner_preview.py)
# ---------------------------------------------------------------------------

WORKSPACE_ID = uuid.UUID("aaaaaaaa-0000-0000-0000-000000000003")
USER_ID = uuid.UUID("bbbbbbbb-0000-0000-0000-000000000003")


async def _insert_org(session: AsyncSession, org_id: uuid.UUID) -> None:
    await session.execute(
        sa.text(
            "INSERT INTO organizations "
            "(id, workspace_id, name, org_type, is_active, version) "
            "VALUES (:id, :ws, 'Test Org Exec', 'internal', true, 1) "
            "ON CONFLICT DO NOTHING"
        ),
        {"id": org_id, "ws": WORKSPACE_ID},
    )


async def _insert_protocol(
    session: AsyncSession,
    protocol_id: uuid.UUID,
    *,
    name: str = "Protocol",
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
            "name": name,
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


async def _insert_plate(
    session: AsyncSession,
    plate_id: uuid.UUID,
    run_id: uuid.UUID,
    *,
    barcode: str | None = None,
    plate_number: int = 1,
) -> None:
    await session.execute(
        sa.text(
            "INSERT INTO plates "
            "(id, run_id, plate_number, barcode) "
            "VALUES (:id, :run_id, :plate_number, :barcode)"
        ),
        {
            "id": plate_id,
            "run_id": run_id,
            "plate_number": plate_number,
            "barcode": barcode,
        },
    )


async def _insert_project(
    session: AsyncSession,
    project_id: uuid.UUID,
    *,
    name: str = "Project",
) -> None:
    await session.execute(
        sa.text(
            "INSERT INTO projects "
            "(id, workspace_id, name, status, created_by, version) "
            "VALUES (:id, :ws, :name, 'active', :user, 1)"
        ),
        {
            "id": project_id,
            "ws": WORKSPACE_ID,
            "name": name,
            "user": USER_ID,
        },
    )


async def _insert_saved_search(
    session: AsyncSession,
    ss_id: uuid.UUID,
    *,
    project_id: uuid.UUID | None = None,
    name: str = "Search",
) -> None:
    await session.execute(
        sa.text(
            "INSERT INTO saved_searches "
            "(id, workspace_id, name, project_id, query, visibility, created_by, version) "
            "VALUES (:id, :ws, :name, :project_id, :query, 'private', :user, 1)"
        ),
        {
            "id": ss_id,
            "ws": WORKSPACE_ID,
            "name": name,
            "project_id": project_id,
            "query": "{}",
            "user": USER_ID,
        },
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_execute_deletes_protocol_and_descendants(
    db_session: AsyncSession,
) -> None:
    """Cascade-deleting a protocol removes the protocol, its run, and the plate."""
    org_id = uuid.uuid4()
    protocol_id = uuid.uuid4()
    run_id = uuid.uuid4()
    plate_id = uuid.uuid4()

    await _insert_org(db_session, org_id)
    await _insert_protocol(db_session, protocol_id, name="ExecProtocol")
    await _insert_run(db_session, run_id, protocol_id, notes="ExecRun")
    await _insert_plate(db_session, plate_id, run_id, barcode="EXB1")
    await db_session.flush()

    runner = CascadeRunner(db_session)
    entries = await runner.execute(
        parent_table="protocols", parent_id=protocol_id, workspace_id=WORKSPACE_ID
    )
    await db_session.flush()

    # All rows gone
    for table_name in ("protocols", "runs", "plates"):
        t = Base.metadata.tables[table_name]
        # Filter by workspace so other tests' data doesn't interfere
        count = (
            await db_session.execute(
                sa.select(sa.func.count()).select_from(t).where(
                    t.c.id.in_([protocol_id, run_id, plate_id])
                )
            )
        ).scalar_one()
        assert count == 0, f"{table_name} row should have been deleted"

    # Audit entries cover every deleted row (protocol + run + plate at least)
    assert len(entries) >= 3, f"expected ≥3 audit entries, got {len(entries)}"
    entity_types = {e.entity_type for e in entries}
    assert "protocol" in entity_types
    assert "run" in entity_types
    assert "plate" in entity_types

    # Each entry has action=DELETE and old_value set
    for entry in entries:
        assert entry.action.value == "delete"
        assert entry.old_value is not None
        assert entry.new_value is None


@pytest.mark.asyncio
async def test_execute_sets_null_on_saved_searches(
    db_session: AsyncSession,
) -> None:
    """Cascade-deleting a project NULLs saved_search.project_id (SET NULL rule)."""
    project_id = uuid.uuid4()
    saved_search_id = uuid.uuid4()

    await _insert_project(db_session, project_id, name="ExecProject")
    await _insert_saved_search(
        db_session, saved_search_id, project_id=project_id, name="ExecSearch"
    )
    await db_session.flush()

    runner = CascadeRunner(db_session)
    entries = await runner.execute(
        parent_table="projects", parent_id=project_id, workspace_id=WORKSPACE_ID
    )
    await db_session.flush()

    # Project is gone
    projects_t = Base.metadata.tables["projects"]
    proj_count = (
        await db_session.execute(
            sa.select(sa.func.count()).select_from(projects_t).where(
                projects_t.c.id == project_id
            )
        )
    ).scalar_one()
    assert proj_count == 0, "project row should have been deleted"

    # Saved search still exists but its project_id is NULL
    ss_table = Base.metadata.tables["saved_searches"]
    row = (
        await db_session.execute(
            sa.select(ss_table.c.project_id).where(ss_table.c.id == saved_search_id)
        )
    ).scalar_one()
    assert row is None, f"saved_search.project_id should be NULL, got {row!r}"

    # Audit entries include the project itself
    assert len(entries) >= 1
    entity_types = {e.entity_type for e in entries}
    assert "project" in entity_types
