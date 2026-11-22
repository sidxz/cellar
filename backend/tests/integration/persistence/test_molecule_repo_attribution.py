"""Who registered a molecule, their Duar org, and the discloser's org survive a save and reload."""

from __future__ import annotations

import uuid

import pytest
import sqlalchemy as sa

from cellar.domain.chemical_registration.enums import MoleculeType
from cellar.domain.chemical_registration.molecule import Molecule
from cellar.domain.shared.value_objects import RegistrationNumber
from cellar.infrastructure.persistence.sqlalchemy.chemical_registration.molecule_repository import (
    SQLAlchemyMoleculeRepository,
)
from cellar.infrastructure.persistence.unit_of_work import AsyncUnitOfWork


@pytest.mark.asyncio
async def test_registrant_and_discloser_orgs_round_trip(uow: AsyncUnitOfWork) -> None:
    ws, local_org, user, duar_org, discloser_org = (uuid.uuid4() for _ in range(5))
    mol = Molecule.register_undisclosed(
        workspace_id=ws,
        registration_number=RegistrationNumber(value=f"CV-{uuid.uuid4().hex[:6]}"),
        name="Partner compound",
        molecule_type=MoleculeType.SMALL_MOLECULE,
        originating_org_id=local_org,
        registered_by=user,
        registered_by_org_id=duar_org,
    )
    mol.disclosed_by_org_id = discloser_org  # mapping check only

    async with uow:
        await uow.session.execute(
            sa.text(
                "INSERT INTO organizations (id, workspace_id, name, org_type, is_active, version) "
                "VALUES (:id, :ws, 'Local', 'internal', true, 1)"
            ),
            {"id": local_org, "ws": ws},
        )
        await SQLAlchemyMoleculeRepository(uow).save(mol)
        await uow.commit()

    async with uow:
        loaded = await SQLAlchemyMoleculeRepository(uow).find_by_id_in_workspace(ws, mol.id)

    assert loaded is not None
    assert (loaded.registered_by, loaded.registered_by_org_id) == (user, duar_org)
    assert loaded.disclosed_by_org_id == discloser_org
