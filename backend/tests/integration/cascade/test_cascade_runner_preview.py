"""Integration tests: CascadeRunner preview engine.

Uses raw SQL inserts (same pattern as test_inbound_refs.py) to avoid
dependency on domain factories.

RunModel has no ``name`` column — ``notes`` is used as the human label
for runs in TABLE_LABELS.  PlateModel uses ``barcode``.

The cascade rules module must be imported explicitly so the process-global
registry is populated before CascadeRunner.preview() calls get_rules_for_parent().
"""
from __future__ import annotations

import uuid
from datetime import date

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

# Force cascade rules into the registry
import chem_vault.domain.screening_assay.cascade  # noqa: F401
# Force models into Base.metadata (screening assay models cover runs/plates)
import chem_vault.infrastructure.persistence.sqlalchemy.screening_assay.models  # noqa: F401

from chem_vault.domain.shared.cascade import CascadeAction
from chem_vault.infrastructure.cascade.cascade_runner import CascadeRunner


# ---------------------------------------------------------------------------
# Stable IDs and raw SQL helpers
# ---------------------------------------------------------------------------

WORKSPACE_ID = uuid.UUID("aaaaaaaa-0000-0000-0000-000000000002")
USER_ID = uuid.UUID("bbbbbbbb-0000-0000-0000-000000000002")


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


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_preview_protocol_with_one_run_one_plate(
    db_session: AsyncSession,
) -> None:
    """Protocol → Run → Plate cascade tree is built correctly."""
    org_id = uuid.uuid4()
    protocol_id = uuid.uuid4()
    run_id = uuid.uuid4()
    plate_id = uuid.uuid4()

    await _insert_org(db_session, org_id)
    await _insert_protocol(db_session, protocol_id, name="P1")
    await _insert_run(db_session, run_id, protocol_id, notes="R1")
    await _insert_plate(db_session, plate_id, run_id, barcode="B1")

    runner = CascadeRunner(db_session)
    tree = await runner.preview(parent_table="protocols", parent_id=protocol_id)

    # Root node
    assert tree.entity_type == "protocol"
    assert tree.count == 1
    assert tree.table == "protocols"

    # Runs child node
    runs_node = next((c for c in tree.children if c.table == "runs"), None)
    assert runs_node is not None, f"expected 'runs' child, got: {[c.table for c in tree.children]}"
    assert runs_node.count == 1
    assert runs_node.action == CascadeAction.CASCADE

    # Because runs has recurse_into_entity="run", the runner adds one sub-node
    # per sample row.  That sub-node is seeded from run_id and walks run's children.
    assert len(runs_node.children) == 1, "expected one recursed run sub-node"
    run_sub = runs_node.children[0]

    # Plates are children of the run sub-node
    plates_node = next(
        (c for c in run_sub.children if c.table == "plates"), None
    )
    assert plates_node is not None, (
        f"expected 'plates' child in run sub-node, got: {[c.table for c in run_sub.children]}"
    )
    assert plates_node.count == 1
    assert plates_node.action == CascadeAction.CASCADE
