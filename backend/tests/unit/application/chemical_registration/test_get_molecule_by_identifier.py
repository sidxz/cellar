"""Tests for GetMoleculeByIdentifier query use case."""

from __future__ import annotations

import uuid
from types import TracebackType
from typing import Self

import pytest
from returns.result import Failure, Success

from cellar.application.chemical_registration.get_molecule_by_identifier import (
    GetMoleculeByIdentifier,
    GetMoleculeByIdentifierQuery,
)
from cellar.domain.chemical_registration.enums import IdentifierType, MoleculeType
from cellar.domain.chemical_registration.molecule import Molecule
from cellar.domain.chemical_registration.molecule_identifier import MoleculeIdentifier
from cellar.domain.shared.errors import NotFoundError
from cellar.domain.shared.events import DomainEvent
from cellar.domain.shared.value_objects import RegistrationNumber

# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------

WS_ID = uuid.uuid4()
ORG_ID = uuid.uuid4()
USER_ID = uuid.uuid4()


class FakeUnitOfWork:
    async def commit(self) -> list[DomainEvent]:
        return []

    async def rollback(self) -> None:
        pass

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        pass


class FakeMoleculeRepository:
    def __init__(self) -> None:
        self._store: dict[uuid.UUID, Molecule] = {}

    def add(self, mol: Molecule) -> None:
        self._store[mol.id] = mol

    async def find_by_identifier(
        self, workspace_id: uuid.UUID, identifier: str
    ) -> Molecule | None:
        for m in self._store.values():
            if m.workspace_id != workspace_id:
                continue
            for ident in m.identifiers:
                if ident.identifier == identifier:
                    return m
        return None


def _make_mol_with_identifier(identifier: str) -> Molecule:
    mol = Molecule.register_undisclosed(
        workspace_id=WS_ID,
        registration_number=RegistrationNumber(value="CV-00001"),
        name="Test compound",
        molecule_type=MoleculeType.SMALL_MOLECULE,
        originating_org_id=ORG_ID,
    )
    mol.add_identifier(
        MoleculeIdentifier.create(
            molecule_id=mol.id,
            identifier=identifier,
            identifier_type=IdentifierType.VENDOR_ID,
            source="test",
            registered_by=USER_ID,
        )
    )
    mol.clear_events()
    return mol


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestGetMoleculeByIdentifier:
    @pytest.mark.asyncio
    async def test_found(self) -> None:
        repo = FakeMoleculeRepository()
        mol = _make_mol_with_identifier("ABBVIE-002")
        repo.add(mol)

        uc = GetMoleculeByIdentifier(FakeUnitOfWork(), repo)
        result = await uc(
            GetMoleculeByIdentifierQuery(workspace_id=WS_ID, identifier="ABBVIE-002")
        )

        assert isinstance(result, Success)
        assert result.unwrap().id == mol.id

    @pytest.mark.asyncio
    async def test_not_found(self) -> None:
        repo = FakeMoleculeRepository()
        uc = GetMoleculeByIdentifier(FakeUnitOfWork(), repo)

        result = await uc(
            GetMoleculeByIdentifierQuery(workspace_id=WS_ID, identifier="NONEXIST")
        )

        assert isinstance(result, Failure)
        assert isinstance(result.failure(), NotFoundError)

    @pytest.mark.asyncio
    async def test_wrong_workspace(self) -> None:
        repo = FakeMoleculeRepository()
        mol = _make_mol_with_identifier("ABBVIE-002")
        repo.add(mol)

        uc = GetMoleculeByIdentifier(FakeUnitOfWork(), repo)
        result = await uc(
            GetMoleculeByIdentifierQuery(
                workspace_id=uuid.uuid4(), identifier="ABBVIE-002"
            )
        )

        assert isinstance(result, Failure)
        assert isinstance(result.failure(), NotFoundError)
