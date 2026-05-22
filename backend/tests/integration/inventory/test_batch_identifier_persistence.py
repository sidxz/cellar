"""Integration: BatchIdentifier round-trips derived_from_molecule_identifier_id."""

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


async def _insert_molecule(
    uow: AsyncUnitOfWork, mol_id: uuid.UUID, ws_id: uuid.UUID, reg: str
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
        {"id": mol_id, "ws": ws_id, "name": f"M-{reg}", "reg": reg, "org": org_id},
    )


async def _insert_molecule_identifier(
    uow: AsyncUnitOfWork,
    ident_id: uuid.UUID,
    mol_id: uuid.UUID,
    ws_id: uuid.UUID,
    identifier: str,
    actor: uuid.UUID,
) -> None:
    await uow.session.execute(
        sa.text(
            "INSERT INTO molecule_identifiers "
            "(id, molecule_id, workspace_id, identifier, identifier_type, source, registered_by) "
            "VALUES (:id, :mol, :ws, :ident, 'custom', 'Registration', :actor)"
        ),
        {"id": ident_id, "mol": mol_id, "ws": ws_id, "ident": identifier, "actor": actor},
    )


async def _insert_batch(
    uow: AsyncUnitOfWork,
    mol_id: uuid.UUID,
    ws_id: uuid.UUID,
    batch_id: uuid.UUID,
    bn: str,
    actor: uuid.UUID,
) -> None:
    await uow.session.execute(
        sa.text(
            "INSERT INTO batches (id, workspace_id, molecule_id, batch_number, "
            "amount_value, amount_unit, source, chemist, version) "
            "VALUES (:id, :ws, :mol, :bn, 1.0, 'mg', 'synthesized', :chem, 1)"
        ),
        {"id": batch_id, "ws": ws_id, "mol": mol_id, "bn": bn, "chem": actor},
    )


@pytest.mark.integration
class TestBatchIdentifierDerivedFromPersistence:

    async def test_round_trips_derived_from_fk(self, uow: AsyncUnitOfWork) -> None:
        """A BatchIdentifier with derived_from_molecule_identifier_id survives save→reload."""
        ws = uuid.uuid4()
        mol_id = uuid.uuid4()
        mol_ident_id = uuid.uuid4()
        batch_id = uuid.uuid4()
        actor = uuid.uuid4()

        async with uow:
            await _insert_molecule(uow, mol_id, ws, "CC-000001")
            await _insert_molecule_identifier(uow, mol_ident_id, mol_id, ws, "SACC-0001", actor)
            await _insert_batch(uow, mol_id, ws, batch_id, "CC-000001-001", actor)
            await uow.commit()

        async with uow:
            repo = SQLAlchemyBatchRepository(uow)
            batch = await repo.find_by_batch_number(ws, "CC-000001-001")
            assert batch is not None

            mirror = BatchIdentifier.create(
                batch_id=batch.id,
                identifier="SACC-0001-001",
                identifier_type="custom",
                source="compound-syn",
                registered_by=actor,
                derived_from_molecule_identifier_id=mol_ident_id,
            )
            manual = BatchIdentifier.create(
                batch_id=batch.id,
                identifier="VENDOR-LOT-Z9",
                identifier_type="external_lot",
                source="chemist input",
                registered_by=actor,
            )
            batch.add_identifier(mirror)
            batch.add_identifier(manual)
            await repo.save(batch)
            await uow.commit()

        async with uow:
            repo = SQLAlchemyBatchRepository(uow)
            loaded = await repo.find_by_batch_number(ws, "CC-000001-001")

        assert loaded is not None
        by_str = {i.identifier: i for i in loaded.identifiers}
        assert by_str["SACC-0001-001"].derived_from_molecule_identifier_id == mol_ident_id
        assert by_str["VENDOR-LOT-Z9"].derived_from_molecule_identifier_id is None

    async def test_cascade_delete_via_fk_removes_mirrors(self, uow: AsyncUnitOfWork) -> None:
        """Deleting a molecule_identifiers row cascades and removes derived batch identifiers."""
        ws = uuid.uuid4()
        mol_id = uuid.uuid4()
        mol_ident_id = uuid.uuid4()
        batch_id = uuid.uuid4()
        actor = uuid.uuid4()

        async with uow:
            await _insert_molecule(uow, mol_id, ws, "CC-000002")
            await _insert_molecule_identifier(uow, mol_ident_id, mol_id, ws, "SACC-0002", actor)
            await _insert_batch(uow, mol_id, ws, batch_id, "CC-000002-001", actor)
            # Insert a derived batch identifier directly via SQL
            bi_id = uuid.uuid4()
            await uow.session.execute(
                sa.text(
                    "INSERT INTO batch_identifiers "
                    "(id, batch_id, workspace_id, identifier, identifier_type, source, "
                    "registered_by, derived_from_molecule_identifier_id) "
                    "VALUES (:id, :bid, :ws, 'SACC-0002-001', 'custom', 'compound-syn', "
                    ":actor, :mident)"
                ),
                {"id": bi_id, "bid": batch_id, "ws": ws, "actor": actor, "mident": mol_ident_id},
            )
            await uow.commit()

        # Delete the parent molecule_identifier — should cascade to batch_identifiers
        async with uow:
            await uow.session.execute(
                sa.text("DELETE FROM molecule_identifiers WHERE id = :id"),
                {"id": mol_ident_id},
            )
            await uow.commit()

        async with uow:
            r = await uow.session.execute(
                sa.text(
                    "SELECT COUNT(*) FROM batch_identifiers "
                    "WHERE derived_from_molecule_identifier_id = :id"
                ),
                {"id": mol_ident_id},
            )
            count = r.scalar_one()
        assert count == 0
