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
import cellar.infrastructure.cascade.rules_screening_assay  # noqa: F401
import cellar.infrastructure.cascade.rules_research_organization  # noqa: F401

# Force models into Base.metadata
import cellar.infrastructure.persistence.sqlalchemy.screening_assay.models  # noqa: F401
import cellar.infrastructure.persistence.sqlalchemy.research_organization.models  # noqa: F401

from cellar.infrastructure.cascade.cascade_runner import CascadeRunner
from cellar.infrastructure.persistence.sqlalchemy.base import Base


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


async def _insert_readout_definition(
    session: AsyncSession,
    rd_id: uuid.UUID,
    protocol_id: uuid.UUID,
    *,
    name: str = "Signal",
) -> None:
    await session.execute(
        sa.text(
            "INSERT INTO readout_definitions "
            "(id, protocol_id, name, data_type, aggregation, display_order) "
            "VALUES (:id, :proto, :name, 'numeric', 'none', 0)"
        ),
        {"id": rd_id, "proto": protocol_id, "name": name},
    )


async def _insert_readout_data(
    session: AsyncSession,
    rdata_id: uuid.UUID,
    run_id: uuid.UUID,
    readout_definition_id: uuid.UUID,
    *,
    value_numeric: float = 1.0,
) -> None:
    await session.execute(
        sa.text(
            "INSERT INTO readout_data "
            "(id, workspace_id, run_id, readout_definition_id, value_numeric) "
            "VALUES (:id, :ws, :run_id, :rd_id, :v)"
        ),
        {
            "id": rdata_id,
            "ws": WORKSPACE_ID,
            "run_id": run_id,
            "rd_id": readout_definition_id,
            "v": value_numeric,
        },
    )


@pytest.mark.asyncio
async def test_execute_deletes_protocol_with_readout_data(
    db_session: AsyncSession,
) -> None:
    """Regression: protocol cascade must delete readout_data BEFORE runs.

    readout_data.run_id is FK with no ondelete, so the cascade runner must
    order DELETEs so that grandchildren go before their parents. Earlier
    versions inverted this and hit ForeignKeyViolationError when deleting a
    protocol whose runs had any readout_data rows.
    """
    org_id = uuid.uuid4()
    protocol_id = uuid.uuid4()
    run_id = uuid.uuid4()
    rd_id = uuid.uuid4()
    rdata_id = uuid.uuid4()

    await _insert_org(db_session, org_id)
    await _insert_protocol(db_session, protocol_id, name="ReadoutProtocol")
    await _insert_readout_definition(db_session, rd_id, protocol_id)
    await _insert_run(db_session, run_id, protocol_id, notes="ReadoutRun")
    await _insert_readout_data(db_session, rdata_id, run_id, rd_id, value_numeric=42.0)
    await db_session.flush()

    runner = CascadeRunner(db_session)
    await runner.execute(
        parent_table="protocols", parent_id=protocol_id, workspace_id=WORKSPACE_ID
    )
    await db_session.flush()

    for table_name, row_id in (
        ("protocols", protocol_id),
        ("runs", run_id),
        ("readout_definitions", rd_id),
        ("readout_data", rdata_id),
    ):
        t = Base.metadata.tables[table_name]
        count = (
            await db_session.execute(
                sa.select(sa.func.count()).select_from(t).where(t.c.id == row_id)
            )
        ).scalar_one()
        assert count == 0, f"{table_name} row {row_id} should have been deleted"


async def _insert_protocol_with_parent(
    session: AsyncSession,
    protocol_id: uuid.UUID,
    parent_protocol_id: uuid.UUID,
    *,
    name: str = "Successor",
) -> None:
    await session.execute(
        sa.text(
            "INSERT INTO protocols "
            "(id, workspace_id, name, protocol_type, status, "
            "is_locked, dose_unit, pos_control_signal, version, protocol_version, "
            "created_by, parent_protocol_id) "
            "VALUES (:id, :ws, :name, 'biochemical', 'active', "
            "false, 'uM', 'high', 1, 2, :user, :parent)"
        ),
        {
            "id": protocol_id,
            "ws": WORKSPACE_ID,
            "name": name,
            "user": USER_ID,
            "parent": parent_protocol_id,
        },
    )


@pytest.mark.asyncio
async def test_execute_clears_successor_protocol_lineage(
    db_session: AsyncSession,
) -> None:
    """Regression: cascade-deleting a protocol must NULL parent_protocol_id on
    successor protocols, not block on the self-referential FK.

    Production hit ForeignKeyViolationError on protocols_parent_protocol_id_fkey
    because no Tier-2 rule existed for the self-ref. Successors are independent
    aggregates — they should survive with their lineage link cleared.
    """
    org_id = uuid.uuid4()
    parent_protocol_id = uuid.uuid4()
    successor_protocol_id = uuid.uuid4()

    await _insert_org(db_session, org_id)
    await _insert_protocol(db_session, parent_protocol_id, name="ParentProtocol")
    await _insert_protocol_with_parent(
        db_session,
        successor_protocol_id,
        parent_protocol_id,
        name="SuccessorProtocol",
    )
    await db_session.flush()

    runner = CascadeRunner(db_session)
    await runner.execute(
        parent_table="protocols",
        parent_id=parent_protocol_id,
        workspace_id=WORKSPACE_ID,
    )
    await db_session.flush()

    protocols_t = Base.metadata.tables["protocols"]

    parent_count = (
        await db_session.execute(
            sa.select(sa.func.count())
            .select_from(protocols_t)
            .where(protocols_t.c.id == parent_protocol_id)
        )
    ).scalar_one()
    assert parent_count == 0, "parent protocol should have been deleted"

    successor_parent_id = (
        await db_session.execute(
            sa.select(protocols_t.c.parent_protocol_id).where(
                protocols_t.c.id == successor_protocol_id
            )
        )
    ).scalar_one()
    assert successor_parent_id is None, (
        f"successor protocol should survive with parent_protocol_id NULLed, "
        f"got {successor_parent_id!r}"
    )


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
