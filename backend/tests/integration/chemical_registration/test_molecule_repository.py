"""Integration tests for MoleculeRepository.find_undisclosed_by_identifiers."""

from __future__ import annotations

import uuid

import pytest
import sqlalchemy as sa

from cellar.infrastructure.persistence.sqlalchemy.chemical_registration.molecule_repository import (
    SQLAlchemyMoleculeRepository,
)
from cellar.infrastructure.persistence.unit_of_work import AsyncUnitOfWork


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _ensure_org(uow: AsyncUnitOfWork, org_id: uuid.UUID, ws_id: uuid.UUID) -> None:
    """Insert an organization row (idempotent) needed as FK target for molecules."""
    await uow.session.execute(
        sa.text(
            "INSERT INTO organizations (id, workspace_id, name, org_type, is_active, version) "
            "VALUES (:id, :ws, 'Test Org', 'internal', true, 1) "
            "ON CONFLICT DO NOTHING"
        ),
        {"id": org_id, "ws": ws_id},
    )


async def _insert_molecule_raw(
    uow: AsyncUnitOfWork,
    mol_id: uuid.UUID,
    ws_id: uuid.UUID,
    reg_num: str,
    *,
    structure_status: str = "undisclosed",
    merged_into_id: uuid.UUID | None = None,
) -> None:
    """Insert a minimal molecule row directly via SQL."""
    org_id = ws_id
    await _ensure_org(uow, org_id, ws_id)
    await uow.session.execute(
        sa.text(
            "INSERT INTO molecules "
            "(id, workspace_id, name, molecule_type, structure_status, "
            "registration_status, synthesis_status, lifecycle_stage, "
            "registration_number, originating_org_id, merged_into_id, version) "
            "VALUES (:id, :ws, :name, 'small_molecule', :ss, "
            "'approved', 'virtual', 'registered', :reg, :org, :merged, 1)"
        ),
        {
            "id": mol_id,
            "ws": ws_id,
            "name": f"Mol-{reg_num}",
            "reg": reg_num,
            "org": org_id,
            "ss": structure_status,
            "merged": merged_into_id,
        },
    )


async def _insert_identifier_raw(
    uow: AsyncUnitOfWork,
    mol_id: uuid.UUID,
    ws_id: uuid.UUID,
    identifier: str,
) -> None:
    """Insert a molecule_identifier row directly via SQL."""
    ident_id = uuid.uuid4()
    user_id = uuid.uuid4()
    await uow.session.execute(
        sa.text(
            "INSERT INTO molecule_identifiers "
            "(id, molecule_id, workspace_id, identifier, identifier_type, source, registered_by) "
            "VALUES (:id, :mol, :ws, :ident, 'external', 'test', :user)"
        ),
        {
            "id": ident_id,
            "mol": mol_id,
            "ws": ws_id,
            "ident": identifier,
            "user": user_id,
        },
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestFindUndisclosedByIdentifiers:

    async def test_single_match(self, uow: AsyncUnitOfWork) -> None:
        """An undisclosed molecule with a matching identifier is returned."""
        ws_id = uuid.uuid4()
        mol_id = uuid.uuid4()

        async with uow:
            await _insert_molecule_raw(uow, mol_id, ws_id, "CV-90001", structure_status="undisclosed")
            await _insert_identifier_raw(uow, mol_id, ws_id, "EXT-001")
            await uow.commit()

        async with uow:
            repo = SQLAlchemyMoleculeRepository(uow)
            result = await repo.find_undisclosed_by_identifiers(ws_id, {"EXT-001"})
            assert result is not None
            assert result.id == mol_id

    async def test_no_match(self, uow: AsyncUnitOfWork) -> None:
        """Searching for a nonexistent identifier returns None."""
        ws_id = uuid.uuid4()

        async with uow:
            repo = SQLAlchemyMoleculeRepository(uow)
            result = await repo.find_undisclosed_by_identifiers(ws_id, {"DOES-NOT-EXIST"})
            assert result is None

    async def test_ambiguous_returns_none(self, uow: AsyncUnitOfWork) -> None:
        """When identifiers map to two different undisclosed molecules, returns None."""
        ws_id = uuid.uuid4()
        mol_a = uuid.uuid4()
        mol_b = uuid.uuid4()

        async with uow:
            await _insert_molecule_raw(uow, mol_a, ws_id, "CV-90010", structure_status="undisclosed")
            await _insert_identifier_raw(uow, mol_a, ws_id, "AMB-A")
            await _insert_molecule_raw(uow, mol_b, ws_id, "CV-90011", structure_status="undisclosed")
            await _insert_identifier_raw(uow, mol_b, ws_id, "AMB-B")
            await uow.commit()

        async with uow:
            repo = SQLAlchemyMoleculeRepository(uow)
            result = await repo.find_undisclosed_by_identifiers(ws_id, {"AMB-A", "AMB-B"})
            assert result is None

    async def test_skips_disclosed(self, uow: AsyncUnitOfWork) -> None:
        """A disclosed molecule with a matching identifier is NOT returned."""
        ws_id = uuid.uuid4()
        mol_id = uuid.uuid4()

        async with uow:
            await _insert_molecule_raw(uow, mol_id, ws_id, "CV-90020", structure_status="disclosed")
            await _insert_identifier_raw(uow, mol_id, ws_id, "DISC-001")
            await uow.commit()

        async with uow:
            repo = SQLAlchemyMoleculeRepository(uow)
            result = await repo.find_undisclosed_by_identifiers(ws_id, {"DISC-001"})
            assert result is None

    async def test_case_insensitive_match(self, uow: AsyncUnitOfWork) -> None:
        """Identifier matching is case-insensitive."""
        ws_id = uuid.uuid4()
        mol_id = uuid.uuid4()

        async with uow:
            await _insert_molecule_raw(uow, mol_id, ws_id, "CV-90030", structure_status="undisclosed")
            await _insert_identifier_raw(uow, mol_id, ws_id, "CaSe-MiXeD")
            await uow.commit()

        async with uow:
            repo = SQLAlchemyMoleculeRepository(uow)
            result = await repo.find_undisclosed_by_identifiers(ws_id, {"case-mixed"})
            assert result is not None
            assert result.id == mol_id

    async def test_skips_tombstones(self, uow: AsyncUnitOfWork) -> None:
        """Undisclosed molecule that is a tombstone (merged_into_id set) is NOT returned."""
        ws_id = uuid.uuid4()
        mol_id = uuid.uuid4()
        target_id = uuid.uuid4()

        async with uow:
            # Create the target first so the tombstone's merged_into_id is valid conceptually
            await _insert_molecule_raw(uow, target_id, ws_id, "CV-90040", structure_status="undisclosed")
            await _insert_molecule_raw(
                uow, mol_id, ws_id, "CV-90041",
                structure_status="undisclosed",
                merged_into_id=target_id,
            )
            await _insert_identifier_raw(uow, mol_id, ws_id, "TOMB-001")
            await uow.commit()

        async with uow:
            repo = SQLAlchemyMoleculeRepository(uow)
            result = await repo.find_undisclosed_by_identifiers(ws_id, {"TOMB-001"})
            assert result is None

    async def test_empty_identifiers_returns_none(self, uow: AsyncUnitOfWork) -> None:
        """Passing an empty set of identifiers returns None immediately."""
        ws_id = uuid.uuid4()

        async with uow:
            repo = SQLAlchemyMoleculeRepository(uow)
            result = await repo.find_undisclosed_by_identifiers(ws_id, set())
            assert result is None
