"""Integration tests: RegisterMolecule populates bemis_murcko_smiles.

Exercises the full stack: StructureProcessor (with real RDKit scaffold
calculator) -> RegisterMolecule use case -> SQLAlchemyMoleculeRepository.
"""

from __future__ import annotations

import uuid

import pytest
import sqlalchemy as sa
from returns.result import Success

from cellar.application.chemical_registration.register_molecule import (
    RegisterMolecule,
    RegisterMoleculeCommand,
)
from cellar.infrastructure.messaging.event_dispatcher import EventDispatcher
from cellar.infrastructure.persistence.sqlalchemy.chemical_registration.molecule_repository import (
    SQLAlchemyMoleculeRepository,
)
from cellar.infrastructure.persistence.unit_of_work import AsyncUnitOfWork
from cellar.infrastructure.rdkit.scaffold_calculator import MurckoScaffoldCalculator
from cellar.infrastructure.rdkit.structure_processor import StructureProcessor
from tests.fakes.fake_auth import FakeAuth


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _ensure_org(uow: AsyncUnitOfWork, org_id: uuid.UUID, ws_id: uuid.UUID) -> None:
    """Insert an organization row needed as FK target for molecules."""
    await uow.session.execute(
        sa.text(
            "INSERT INTO organizations (id, workspace_id, name, org_type, is_active, version) "
            "VALUES (:id, :ws, 'Test Org', 'internal', true, 1) "
            "ON CONFLICT DO NOTHING"
        ),
        {"id": org_id, "ws": ws_id},
    )


def _make_use_case(uow: AsyncUnitOfWork) -> RegisterMolecule:
    repo = SQLAlchemyMoleculeRepository(uow)
    dispatcher = EventDispatcher()
    processor = StructureProcessor(scaffold_calculator=MurckoScaffoldCalculator())
    return RegisterMolecule(
        uow=uow,
        repo=repo,
        dispatcher=dispatcher,
        structure_processor=processor,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_register_molecule_persists_scaffold(uow: AsyncUnitOfWork) -> None:
    """Registering ibuprofen stores 'c1ccccc1' as the Bemis-Murcko scaffold."""
    ws_id = uuid.uuid4()
    org_id = uuid.uuid4()

    async with uow:
        await _ensure_org(uow, org_id, ws_id)
        await uow.commit()

    use_case = _make_use_case(uow)
    cmd = RegisterMoleculeCommand(
        workspace_id=ws_id,
        name="Ibuprofen",
        smiles="CC(C)Cc1ccc(cc1)C(C)C(=O)O",
        originating_org_id=org_id,
        registered_by=uuid.uuid4(),
    )
    result = await use_case(cmd, auth=FakeAuth(role="editor"))

    assert isinstance(result, Success)
    mol = result.unwrap().molecule
    assert mol.bemis_murcko_smiles == "c1ccccc1"


@pytest.mark.asyncio
async def test_register_acyclic_records_empty_scaffold(uow: AsyncUnitOfWork) -> None:
    """Registering an acyclic compound stores '' (empty string) as the scaffold."""
    ws_id = uuid.uuid4()
    org_id = uuid.uuid4()

    async with uow:
        await _ensure_org(uow, org_id, ws_id)
        await uow.commit()

    use_case = _make_use_case(uow)
    cmd = RegisterMoleculeCommand(
        workspace_id=ws_id,
        name="Pentane",
        smiles="CCCCC",
        originating_org_id=org_id,
        registered_by=uuid.uuid4(),
    )
    result = await use_case(cmd, auth=FakeAuth(role="editor"))

    assert isinstance(result, Success)
    mol = result.unwrap().molecule
    assert mol.bemis_murcko_smiles == ""
