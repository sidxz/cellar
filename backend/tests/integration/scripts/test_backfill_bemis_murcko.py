"""Integration tests: backfill_bemis_murcko script.

Tests the two key properties of the backfill function:
  1. It populates NULL bemis_murcko_smiles for legacy rows (correct scaffold values).
  2. It is idempotent — a second run processes zero rows.

Uses the same raw-insert helper pattern as
tests/integration/persistence/test_molecule_repo_scaffold_field.py.
Requires the testcontainers PostgreSQL+RDKit fixture (slow, Docker-backed).
"""

from __future__ import annotations

import uuid

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from backfill_bemis_murcko import BackfillBatchStats, backfill_batch
from cellar.infrastructure.persistence.unit_of_work import AsyncUnitOfWork


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _ensure_org(session: AsyncSession, org_id: uuid.UUID, ws_id: uuid.UUID) -> None:
    await session.execute(
        sa.text(
            "INSERT INTO organizations (id, workspace_id, name, org_type, is_active, version) "
            "VALUES (:id, :ws, 'Test Org', 'internal', true, 1) "
            "ON CONFLICT DO NOTHING"
        ),
        {"id": org_id, "ws": ws_id},
    )


async def _insert_molecule(
    session: AsyncSession,
    mol_id: uuid.UUID,
    ws_id: uuid.UUID,
    reg_num: str,
    smiles: str | None,
    *,
    bemis_murcko_smiles: str | None,
) -> None:
    """Insert a minimal molecule row with an explicit bemis_murcko_smiles."""
    org_id = ws_id  # reuse workspace_id as org_id (FK satisfied by _ensure_org)
    await _ensure_org(session, org_id, ws_id)
    await session.execute(
        sa.text(
            "INSERT INTO molecules "
            "(id, workspace_id, name, molecule_type, structure_status, "
            "registration_status, synthesis_status, lifecycle_stage, "
            "registration_number, originating_org_id, smiles, bemis_murcko_smiles, version) "
            "VALUES (:id, :ws, :name, 'small_molecule', 'disclosed', "
            "'approved', 'virtual', 'registered', :reg, :org, :smiles, :bms, 1)"
        ),
        {
            "id": mol_id,
            "ws": ws_id,
            "name": f"Mol-{reg_num}",
            "reg": reg_num,
            "org": org_id,
            "smiles": smiles,
            "bms": bemis_murcko_smiles,
        },
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_backfill_populates_null_rows(uow: AsyncUnitOfWork) -> None:
    """backfill_batch fills NULL scaffold rows with correct Murcko SMILES."""
    ws_id = uuid.uuid4()

    # Three molecules with NULL scaffold; one already populated.
    mol_ids: dict[str, uuid.UUID] = {
        "benzene": uuid.uuid4(),
        "ibuprofen": uuid.uuid4(),
        "pentane": uuid.uuid4(),
        "prefilled": uuid.uuid4(),
    }

    async with uow:
        async_session = uow.session
        await _insert_molecule(
            async_session,
            mol_ids["benzene"],
            ws_id,
            f"CV-BF-{uuid.uuid4().hex[:6]}-1",
            "c1ccccc1",
            bemis_murcko_smiles=None,
        )
        await _insert_molecule(
            async_session,
            mol_ids["ibuprofen"],
            ws_id,
            f"CV-BF-{uuid.uuid4().hex[:6]}-2",
            "CC(C)Cc1ccc(cc1)C(C)C(=O)O",
            bemis_murcko_smiles=None,
        )
        await _insert_molecule(
            async_session,
            mol_ids["pentane"],
            ws_id,
            f"CV-BF-{uuid.uuid4().hex[:6]}-3",
            "CCCCC",
            bemis_murcko_smiles=None,
        )
        await _insert_molecule(
            async_session,
            mol_ids["prefilled"],
            ws_id,
            f"CV-BF-{uuid.uuid4().hex[:6]}-4",
            "c1ccc2ccccc2c1",
            bemis_murcko_smiles="c1ccc2ccccc2c1",  # already set
        )
        await uow.commit()

    async with uow:
        # Scope to this test's workspace — the testcontainer DB is shared
        # across the whole session, so other tests' molecules may also have
        # NULL scaffolds and would inflate the global count.
        stats = await backfill_batch(uow.session, batch_size=10, workspace_id=ws_id)

    assert stats.processed == 3
    assert stats.failed == 0

    # Re-fetch each row and check the scaffold value.
    async with uow:
        for key, mol_id in mol_ids.items():
            row = (
                await uow.session.execute(
                    sa.text("SELECT bemis_murcko_smiles FROM molecules WHERE id = :id"),
                    {"id": mol_id},
                )
            ).one()

            if key == "benzene":
                assert row.bemis_murcko_smiles == "c1ccccc1", (
                    f"Benzene scaffold expected 'c1ccccc1', got {row.bemis_murcko_smiles!r}"
                )
            elif key == "ibuprofen":
                # Ibuprofen's Murcko scaffold is just the phenyl ring.
                assert row.bemis_murcko_smiles == "c1ccccc1", (
                    f"Ibuprofen scaffold expected 'c1ccccc1', got {row.bemis_murcko_smiles!r}"
                )
            elif key == "pentane":
                # Acyclic molecule → empty string (RDKit convention).
                assert row.bemis_murcko_smiles == "", (
                    f"Pentane scaffold expected '', got {row.bemis_murcko_smiles!r}"
                )
            elif key == "prefilled":
                # Already populated — must not be touched.
                assert row.bemis_murcko_smiles == "c1ccc2ccccc2c1", (
                    f"Pre-filled row must be unchanged, got {row.bemis_murcko_smiles!r}"
                )


@pytest.mark.asyncio
async def test_backfill_idempotent(uow: AsyncUnitOfWork) -> None:
    """Running backfill_batch twice processes 0 rows on the second run."""
    ws_id = uuid.uuid4()
    mol_id = uuid.uuid4()

    async with uow:
        await _insert_molecule(
            uow.session,
            mol_id,
            ws_id,
            f"CV-BF-{uuid.uuid4().hex[:6]}-5",
            "c1ccccc1",
            bemis_murcko_smiles=None,
        )
        await uow.commit()

    async with uow:
        first = await backfill_batch(uow.session, batch_size=10, workspace_id=ws_id)

    async with uow:
        second = await backfill_batch(uow.session, batch_size=10, workspace_id=ws_id)

    assert first.processed == 1
    assert first.failed == 0
    assert second.processed == 0
    assert second.failed == 0


@pytest.mark.asyncio
async def test_backfill_handles_none_smiles(uow: AsyncUnitOfWork) -> None:
    """Structureless molecules (smiles=NULL) are marked '' and counted as processed."""
    ws_id = uuid.uuid4()
    mol_id = uuid.uuid4()

    async with uow:
        await _insert_molecule(
            uow.session,
            mol_id,
            ws_id,
            f"CV-BF-{uuid.uuid4().hex[:6]}-6",
            None,  # no SMILES
            bemis_murcko_smiles=None,
        )
        await uow.commit()

    async with uow:
        stats = await backfill_batch(uow.session, batch_size=10, workspace_id=ws_id)

    assert stats.processed == 1
    assert stats.failed == 0

    async with uow:
        row = (
            await uow.session.execute(
                sa.text("SELECT bemis_murcko_smiles FROM molecules WHERE id = :id"),
                {"id": mol_id},
            )
        ).one()
    # Structureless → marked as empty string so it is not retried.
    assert row.bemis_murcko_smiles == ""
