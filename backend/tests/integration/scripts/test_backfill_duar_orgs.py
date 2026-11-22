"""backfill_duar_orgs: existing records take one named Duar org, and the registrant from History."""

from __future__ import annotations

import uuid
from datetime import date

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backfill_duar_orgs import backfill
from tests.integration import _screening_seed as seed

pytestmark = pytest.mark.asyncio

DUAR = uuid.uuid4()


async def _undisclosed(s: AsyncSession, ws: uuid.UUID) -> uuid.UUID:
    mid = uuid.uuid4()
    await s.execute(
        sa.text(
            "INSERT INTO molecules (id, workspace_id, registration_number, name, molecule_type, "
            "structure_status, registration_status, synthesis_status, lifecycle_stage, version) "
            "VALUES (:id, :ws, :reg, 'U', 'small_molecule', 'undisclosed', 'approved', "
            "'virtual', 'registered', 1)"
        ),
        {"id": mid, "ws": ws, "reg": f"CV-{mid.hex[:6]}"},
    )
    return mid


async def _registration_audit(s: AsyncSession, ws: uuid.UUID, mid: uuid.UUID, user: uuid.UUID):
    await s.execute(
        sa.text(
            "INSERT INTO audit_operations (id, workspace_id, operation_type, user_id, actor_type, "
            "entity_type, entity_id, status) "
            "VALUES (:id, :ws, 'registration', :u, 'user', 'Molecule', :m, 'completed')"
        ),
        {"id": uuid.uuid4(), "ws": ws, "u": user, "m": mid},
    )


async def _row(s: AsyncSession, table: str, rid: uuid.UUID) -> dict:
    return dict(
        (await s.execute(sa.text(f"SELECT * FROM {table} WHERE id = :id"), {"id": rid}))
        .mappings()
        .one()
    )  # noqa: S608


async def _seed(sf: async_sessionmaker[AsyncSession]) -> dict:
    ws, user = uuid.uuid4(), uuid.uuid4()
    async with sf() as s, s.begin():
        local = await seed.org(s, ws)
        audited = await seed.molecule(s, ws, local, "Audited")
        unaudited = await seed.molecule(s, ws, local, "No history")
        undisclosed = await _undisclosed(s, ws)
        await _registration_audit(s, ws, audited, user)
        pid = await seed.protocol(s, ws)
        local_run = await seed.run(s, ws, pid, date(2026, 1, 1))
        duar_run = await seed.run(s, ws, pid, date(2026, 1, 2))
        kept = uuid.uuid4()
        await s.execute(
            sa.text("UPDATE runs SET performed_at_org_id = :o WHERE id = :r"),
            {"o": local, "r": local_run},
        )
        await s.execute(
            sa.text("UPDATE runs SET performed_at_org_id = :o WHERE id = :r"),
            {"o": kept, "r": duar_run},
        )
    return dict(
        ws=ws,
        user=user,
        audited=audited,
        unaudited=unaudited,
        undisclosed=undisclosed,
        local_run=local_run,
        duar_run=duar_run,
        kept=kept,
        protocol=pid,
    )


async def test_fills_null_org_columns(session_factory) -> None:
    w = await _seed(session_factory)
    await backfill(session_factory, org_id=DUAR, workspace_id=w["ws"], dry_run=False)
    async with session_factory() as s:
        mol = await _row(s, "molecules", w["audited"])
        protocol = await _row(s, "protocols", w["protocol"])
    assert (mol["registered_by_org_id"], mol["disclosed_by_org_id"]) == (DUAR, DUAR)
    assert (protocol["created_by_org_id"], protocol["owner_org_id"]) == (DUAR, DUAR)


async def test_undisclosed_molecule_gets_no_discloser_org(session_factory) -> None:
    w = await _seed(session_factory)
    await backfill(session_factory, org_id=DUAR, workspace_id=w["ws"], dry_run=False)
    async with session_factory() as s:
        mol = await _row(s, "molecules", w["undisclosed"])
    assert mol["registered_by_org_id"] == DUAR
    assert (mol["disclosed_by"], mol["disclosed_by_org_id"]) == (None, None)


async def test_replaces_local_org_id_on_run(session_factory) -> None:
    w = await _seed(session_factory)
    await backfill(session_factory, org_id=DUAR, workspace_id=w["ws"], dry_run=False)
    async with session_factory() as s:
        assert (await _row(s, "runs", w["local_run"]))["performed_at_org_id"] == DUAR


async def test_keeps_existing_duar_org_on_run(session_factory) -> None:
    w = await _seed(session_factory)
    await backfill(session_factory, org_id=DUAR, workspace_id=w["ws"], dry_run=False)
    async with session_factory() as s:
        assert (await _row(s, "runs", w["duar_run"]))["performed_at_org_id"] == w["kept"]


async def test_second_run_changes_nothing(session_factory) -> None:
    w = await _seed(session_factory)
    await backfill(session_factory, org_id=DUAR, workspace_id=w["ws"], dry_run=False)
    again = await backfill(session_factory, org_id=DUAR, workspace_id=w["ws"], dry_run=False)
    assert set(again.values()) == {0}


async def test_registered_by_from_registration_audit(session_factory) -> None:
    w = await _seed(session_factory)
    await backfill(session_factory, org_id=DUAR, workspace_id=w["ws"], dry_run=False)
    async with session_factory() as s:
        assert (await _row(s, "molecules", w["audited"]))["registered_by"] == w["user"]


async def test_structure_registered_compound_gets_registrant_as_discloser(session_factory) -> None:
    w = await _seed(session_factory)
    await backfill(session_factory, org_id=DUAR, workspace_id=w["ws"], dry_run=False)
    async with session_factory() as s:
        mol = await _row(s, "molecules", w["audited"])
    assert mol["disclosed_by"] == w["user"]
    assert mol["disclosed_at"] == mol["created_at"]


async def test_no_audit_row_leaves_registrant_and_discloser_empty(session_factory) -> None:
    w = await _seed(session_factory)
    await backfill(session_factory, org_id=DUAR, workspace_id=w["ws"], dry_run=False)
    async with session_factory() as s:
        mol = await _row(s, "molecules", w["unaudited"])
    assert (mol["registered_by"], mol["disclosed_by"]) == (None, None)


async def test_dry_run_writes_nothing(session_factory) -> None:
    w = await _seed(session_factory)
    counts = await backfill(session_factory, org_id=DUAR, workspace_id=w["ws"], dry_run=True)
    assert counts["runs.performed_at_org_id"] == 1  # the local one; the Duar one is kept
    async with session_factory() as s:
        assert (await _row(s, "molecules", w["audited"]))["registered_by_org_id"] is None


async def test_workspace_filter(session_factory) -> None:
    w, other = await _seed(session_factory), await _seed(session_factory)
    await backfill(session_factory, org_id=DUAR, workspace_id=w["ws"], dry_run=False)
    async with session_factory() as s:
        assert (await _row(s, "molecules", other["audited"]))["registered_by_org_id"] is None
