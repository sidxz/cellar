"""Integration tests for batch identifier persistence + lookup."""

from __future__ import annotations

import uuid

import pytest
import sqlalchemy as sa

from cellar.domain.inventory.batch_identifier import BatchIdentifier
from cellar.infrastructure.persistence.sqlalchemy.inventory.batch_repository import (
    SQLAlchemyBatchRepository,
)
from cellar.infrastructure.persistence.unit_of_work import AsyncUnitOfWork


async def _ensure_org(uow: AsyncUnitOfWork, org_id: uuid.UUID, ws_id: uuid.UUID) -> None:
    await uow.session.execute(
        sa.text(
            "INSERT INTO organizations (id, workspace_id, name, org_type, is_active, version) "
            "VALUES (:id, :ws, 'Test Org', 'internal', true, 1) "
            "ON CONFLICT DO NOTHING"
        ),
        {"id": org_id, "ws": ws_id},
    )


async def _insert_molecule(uow: AsyncUnitOfWork, mol_id: uuid.UUID, ws_id: uuid.UUID, reg: str) -> None:
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
        {"id": mol_id, "ws": ws_id, "name": f"M-{reg}", "reg": reg, "org": org_id},
    )


async def _insert_batch(uow: AsyncUnitOfWork, mol_id: uuid.UUID, ws_id: uuid.UUID,
                        batch_id: uuid.UUID, bn: str) -> None:
    await uow.session.execute(
        sa.text(
            "INSERT INTO batches (id, workspace_id, molecule_id, batch_number, "
            "amount_value, amount_unit, source, chemist, version) "
            "VALUES (:id, :ws, :mol, :bn, 1.0, 'mg', 'synthesized', :chem, 1)"
        ),
        {"id": batch_id, "ws": ws_id, "mol": mol_id, "bn": bn, "chem": uuid.uuid4()},
    )


@pytest.mark.integration
class TestBatchIdentifierPersistence:

    async def test_save_with_identifiers_roundtrips(self, uow: AsyncUnitOfWork) -> None:
        ws = uuid.uuid4()
        mol = uuid.uuid4()
        async with uow:
            await _insert_molecule(uow, mol, ws, "CC-000001")
            repo = SQLAlchemyBatchRepository(uow)
            bid = uuid.uuid4()
            await _insert_batch(uow, mol, ws, bid, "CC-000001-001")
            batch = await repo.find_by_batch_number(ws, "CC-000001-001")
            assert batch is not None
            ident = BatchIdentifier.create(
                batch_id=batch.id, identifier="SACC-009999-001",
                identifier_type="external_lot", source="CDD",
                registered_by=uuid.uuid4(),
            )
            batch.add_identifier(ident)
            await repo.save(batch)
            await uow.commit()

        async with uow:
            repo = SQLAlchemyBatchRepository(uow)
            reloaded = await repo.find_by_batch_number(ws, "CC-000001-001")
        assert reloaded is not None
        assert len(reloaded.identifiers) == 1
        assert reloaded.identifiers[0].identifier == "SACC-009999-001"

    async def test_find_by_external_identifier_hit(self, uow: AsyncUnitOfWork) -> None:
        ws = uuid.uuid4()
        mol = uuid.uuid4()
        bid = uuid.uuid4()
        async with uow:
            await _insert_molecule(uow, mol, ws, "CC-000001")
            await _insert_batch(uow, mol, ws, bid, "CC-000001-001")
            repo = SQLAlchemyBatchRepository(uow)
            batch = await repo.find_by_batch_number(ws, "CC-000001-001")
            assert batch is not None
            batch.add_identifier(BatchIdentifier.create(
                batch_id=batch.id, identifier="SACC-009999-001",
                identifier_type="external_lot", source="CDD",
                registered_by=uuid.uuid4(),
            ))
            await repo.save(batch)
            await uow.commit()

        async with uow:
            repo = SQLAlchemyBatchRepository(uow)
            found = await repo.find_by_external_identifier(ws, "SACC-009999-001")
        assert found is not None
        assert found.id == bid

    async def test_find_by_external_identifier_miss(self, uow: AsyncUnitOfWork) -> None:
        ws = uuid.uuid4()
        async with uow:
            repo = SQLAlchemyBatchRepository(uow)
            found = await repo.find_by_external_identifier(ws, "NOTHING")
        assert found is None

    async def test_find_by_external_identifier_workspace_scoped(self, uow: AsyncUnitOfWork) -> None:
        ws_a = uuid.uuid4()
        ws_b = uuid.uuid4()
        mol = uuid.uuid4()
        bid = uuid.uuid4()
        async with uow:
            await _insert_molecule(uow, mol, ws_a, "CC-000001")
            await _insert_batch(uow, mol, ws_a, bid, "CC-000001-001")
            repo = SQLAlchemyBatchRepository(uow)
            batch = await repo.find_by_batch_number(ws_a, "CC-000001-001")
            assert batch is not None
            batch.add_identifier(BatchIdentifier.create(
                batch_id=batch.id, identifier="XYZ",
                identifier_type="custom", source="user",
                registered_by=uuid.uuid4(),
            ))
            await repo.save(batch)
            await uow.commit()
        async with uow:
            repo = SQLAlchemyBatchRepository(uow)
            found = await repo.find_by_external_identifier(ws_b, "XYZ")
        assert found is None

    async def test_delete_batch_cascades_identifiers(self, uow: AsyncUnitOfWork) -> None:
        ws = uuid.uuid4()
        mol = uuid.uuid4()
        bid = uuid.uuid4()
        async with uow:
            await _insert_molecule(uow, mol, ws, "CC-000001")
            await _insert_batch(uow, mol, ws, bid, "CC-000001-001")
            repo = SQLAlchemyBatchRepository(uow)
            batch = await repo.find_by_batch_number(ws, "CC-000001-001")
            assert batch is not None
            batch.add_identifier(BatchIdentifier.create(
                batch_id=batch.id, identifier="ALIAS-X",
                identifier_type="custom", source="user",
                registered_by=uuid.uuid4(),
            ))
            await repo.save(batch)
            await uow.commit()

        async with uow:
            await uow.session.execute(
                sa.text("DELETE FROM batches WHERE id = :id"), {"id": bid}
            )
            await uow.commit()

        async with uow:
            r = await uow.session.execute(
                sa.text("SELECT COUNT(*) FROM batch_identifiers WHERE batch_id = :id"),
                {"id": bid},
            )
            count = r.scalar_one()
        assert count == 0
