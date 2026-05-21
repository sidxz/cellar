"""Integration tests for SQLAlchemyBatchRepository — next_batch_number."""

from __future__ import annotations

import uuid

import pytest
import sqlalchemy as sa

from cellar.infrastructure.persistence.sqlalchemy.inventory.batch_repository import (
    SQLAlchemyBatchRepository,
)
from cellar.infrastructure.persistence.unit_of_work import AsyncUnitOfWork


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _ensure_org(uow: AsyncUnitOfWork, org_id: uuid.UUID, ws_id: uuid.UUID) -> None:
    await uow.session.execute(
        sa.text(
            "INSERT INTO organizations (id, workspace_id, name, org_type, is_active, version) "
            "VALUES (:id, :ws, 'Test Org', 'internal', true, 1) "
            "ON CONFLICT DO NOTHING"
        ),
        {"id": org_id, "ws": ws_id},
    )


async def _insert_molecule(
    uow: AsyncUnitOfWork,
    mol_id: uuid.UUID,
    ws_id: uuid.UUID,
    reg_num: str,
) -> None:
    org_id = ws_id
    await _ensure_org(uow, org_id, ws_id)
    await uow.session.execute(
        sa.text(
            "INSERT INTO molecules "
            "(id, workspace_id, name, molecule_type, structure_status, "
            "registration_status, synthesis_status, lifecycle_stage, "
            "registration_number, originating_org_id, version) "
            "VALUES (:id, :ws, :name, 'small_molecule', 'undisclosed', "
            "'approved', 'virtual', 'registered', :reg, :org, 1)"
        ),
        {
            "id": mol_id,
            "ws": ws_id,
            "name": f"Mol-{reg_num}",
            "reg": reg_num,
            "org": org_id,
        },
    )


async def _insert_batch(
    uow: AsyncUnitOfWork,
    mol_id: uuid.UUID,
    ws_id: uuid.UUID,
    batch_number: str,
) -> None:
    await uow.session.execute(
        sa.text(
            "INSERT INTO batches "
            "(id, workspace_id, molecule_id, batch_number, amount_value, amount_unit, "
            "source, chemist, version) "
            "VALUES (:id, :ws, :mol, :bn, 1.0, 'mg', 'synthesized', :chem, 1)"
        ),
        {
            "id": uuid.uuid4(),
            "ws": ws_id,
            "mol": mol_id,
            "bn": batch_number,
            "chem": uuid.uuid4(),
        },
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestNextBatchNumber:

    async def test_first_batch_starts_at_one(self, uow: AsyncUnitOfWork) -> None:
        ws = uuid.uuid4()
        mol = uuid.uuid4()
        async with uow:
            await _insert_molecule(uow, mol, ws, "CC-000001")
            repo = SQLAlchemyBatchRepository(uow)
            bn = await repo.next_batch_number(ws, mol, width=3)
        assert bn.value == "CC-000001-001"

    async def test_continues_after_existing_batches(self, uow: AsyncUnitOfWork) -> None:
        ws = uuid.uuid4()
        mol = uuid.uuid4()
        async with uow:
            await _insert_molecule(uow, mol, ws, "CC-000001")
            for seq in (1, 2, 3):
                await _insert_batch(uow, mol, ws, f"CC-000001-{seq:03d}")
            repo = SQLAlchemyBatchRepository(uow)
            bn = await repo.next_batch_number(ws, mol, width=3)
        assert bn.value == "CC-000001-004"

    async def test_max_not_count_avoids_collision_after_delete(
        self, uow: AsyncUnitOfWork
    ) -> None:
        """Regression: deleting batch -003 must not cause next_batch to reissue -005."""
        ws = uuid.uuid4()
        mol = uuid.uuid4()
        async with uow:
            await _insert_molecule(uow, mol, ws, "CC-000001")
            # Insert 5 batches, then delete -003 (simulating a chemist correction)
            for seq in (1, 2, 3, 4, 5):
                await _insert_batch(uow, mol, ws, f"CC-000001-{seq:03d}")
            await uow.session.execute(
                sa.text(
                    "DELETE FROM batches WHERE workspace_id = :ws "
                    "AND batch_number = 'CC-000001-003'"
                ),
                {"ws": ws},
            )
            repo = SQLAlchemyBatchRepository(uow)
            bn = await repo.next_batch_number(ws, mol, width=3)
        # COUNT-based would emit -005 (count=4, +1) → collision with existing -005.
        # MAX-based correctly emits -006 (max=5, +1).
        assert bn.value == "CC-000001-006"

    async def test_per_molecule_counter_independent(self, uow: AsyncUnitOfWork) -> None:
        ws = uuid.uuid4()
        mol_a = uuid.uuid4()
        mol_b = uuid.uuid4()
        async with uow:
            await _insert_molecule(uow, mol_a, ws, "CC-000001")
            await _insert_molecule(uow, mol_b, ws, "CC-000002")
            await _insert_batch(uow, mol_a, ws, "CC-000001-007")
            repo = SQLAlchemyBatchRepository(uow)
            bn_a = await repo.next_batch_number(ws, mol_a, width=3)
            bn_b = await repo.next_batch_number(ws, mol_b, width=3)
        assert bn_a.value == "CC-000001-008"
        assert bn_b.value == "CC-000002-001"

    async def test_handles_mixed_width_history(self, uow: AsyncUnitOfWork) -> None:
        """A workspace switched widths mid-life: -005 (3-wide) and -0010 (4-wide) coexist."""
        ws = uuid.uuid4()
        mol = uuid.uuid4()
        async with uow:
            await _insert_molecule(uow, mol, ws, "CC-000001")
            await _insert_batch(uow, mol, ws, "CC-000001-005")
            await _insert_batch(uow, mol, ws, "CC-000001-0010")
            repo = SQLAlchemyBatchRepository(uow)
            bn = await repo.next_batch_number(ws, mol, width=4)
        # MAX trailing int across both is 10; next is 11, padded to 4
        assert bn.value == "CC-000001-0011"

    async def test_width_override(self, uow: AsyncUnitOfWork) -> None:
        ws = uuid.uuid4()
        mol = uuid.uuid4()
        async with uow:
            await _insert_molecule(uow, mol, ws, "CC-000001")
            repo = SQLAlchemyBatchRepository(uow)
            bn = await repo.next_batch_number(ws, mol, width=5)
        assert bn.value == "CC-000001-00001"
