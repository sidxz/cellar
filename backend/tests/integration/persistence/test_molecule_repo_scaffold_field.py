"""Integration tests: bemis_murcko_smiles round-trip on MoleculeRepository.

Covers the three distinct 3-tier semantics that Task 13 (BuildScaffoldNetwork)
will rely on:
  - None   → not yet computed (scaffold unknown)
  - ""     → computed and found to be acyclic (no Murcko scaffold)
  - scalar → computed Murcko SMILES
"""

from __future__ import annotations

import uuid

import pytest
import sqlalchemy as sa

from cellar.infrastructure.persistence.sqlalchemy.chemical_registration.molecule_repository import (
    SQLAlchemyMoleculeRepository,
)
from cellar.infrastructure.persistence.unit_of_work import AsyncUnitOfWork


# ---------------------------------------------------------------------------
# Helpers — mirror the pattern in test_molecule_repository.py
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
    bemis_murcko_smiles: str | None,
) -> None:
    """Insert a minimal molecule row with a specific bemis_murcko_smiles value."""
    org_id = ws_id
    await _ensure_org(uow, org_id, ws_id)
    await uow.session.execute(
        sa.text(
            "INSERT INTO molecules "
            "(id, workspace_id, name, molecule_type, structure_status, "
            "registration_status, synthesis_status, lifecycle_stage, "
            "registration_number, originating_org_id, bemis_murcko_smiles, version) "
            "VALUES (:id, :ws, :name, 'small_molecule', 'undisclosed', "
            "'approved', 'virtual', 'registered', :reg, :org, :bms, 1)"
        ),
        {
            "id": mol_id,
            "ws": ws_id,
            "name": f"Mol-{reg_num}",
            "reg": reg_num,
            "org": org_id,
            "bms": bemis_murcko_smiles,
        },
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_round_trip_bemis_murcko_smiles(uow: AsyncUnitOfWork) -> None:
    """A non-null scaffold SMILES stored in the DB is returned on fetch."""
    ws_id = uuid.uuid4()
    mol_id = uuid.uuid4()

    async with uow:
        await _insert_molecule_raw(uow, mol_id, ws_id, "CV-80001", bemis_murcko_smiles="c1ccccc1")
        await uow.commit()

    async with uow:
        repo = SQLAlchemyMoleculeRepository(uow)
        fetched = await repo.find_by_id_in_workspace(ws_id, mol_id)

    assert fetched is not None
    assert fetched.bemis_murcko_smiles == "c1ccccc1"


@pytest.mark.asyncio
async def test_round_trip_none_scaffold(uow: AsyncUnitOfWork) -> None:
    """NULL in the DB (scaffold not yet computed) maps to None on the domain."""
    ws_id = uuid.uuid4()
    mol_id = uuid.uuid4()

    async with uow:
        await _insert_molecule_raw(uow, mol_id, ws_id, "CV-80002", bemis_murcko_smiles=None)
        await uow.commit()

    async with uow:
        repo = SQLAlchemyMoleculeRepository(uow)
        fetched = await repo.find_by_id_in_workspace(ws_id, mol_id)

    assert fetched is not None
    assert fetched.bemis_murcko_smiles is None


@pytest.mark.asyncio
async def test_round_trip_acyclic_empty_string(uow: AsyncUnitOfWork) -> None:
    """Empty string (acyclic molecule — no Murcko scaffold) survives the round-trip."""
    ws_id = uuid.uuid4()
    mol_id = uuid.uuid4()

    async with uow:
        await _insert_molecule_raw(uow, mol_id, ws_id, "CV-80003", bemis_murcko_smiles="")
        await uow.commit()

    async with uow:
        repo = SQLAlchemyMoleculeRepository(uow)
        fetched = await repo.find_by_id_in_workspace(ws_id, mol_id)

    assert fetched is not None
    assert fetched.bemis_murcko_smiles == ""
