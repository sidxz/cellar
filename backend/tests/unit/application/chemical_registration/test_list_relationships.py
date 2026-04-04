"""Tests for ListRelationships query use case."""

from __future__ import annotations

import uuid
from types import TracebackType
from typing import Self

import pytest
from returns.result import Failure, Success

from chem_vault.application.chemical_registration.list_relationships import (
    ListRelationships,
    ListRelationshipsQuery,
)
from chem_vault.domain.chemical_registration.enums import MoleculeType, RelationshipType
from chem_vault.domain.chemical_registration.molecule import Molecule
from chem_vault.domain.chemical_registration.molecule_relationship import MoleculeRelationship
from chem_vault.domain.shared.errors import NotFoundError
from chem_vault.domain.shared.events import DomainEvent
from chem_vault.domain.shared.value_objects import RegistrationNumber

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

    async def find_by_id(self, id: uuid.UUID) -> Molecule | None:
        return self._store.get(id)


class FakeRelationshipRepository:
    def __init__(self) -> None:
        self._store: list[MoleculeRelationship] = []

    def add(self, rel: MoleculeRelationship) -> None:
        self._store.append(rel)

    async def find_by_source(
        self, source_molecule_id: uuid.UUID
    ) -> list[MoleculeRelationship]:
        return [r for r in self._store if r.source_molecule_id == source_molecule_id]

    async def find_by_target(
        self, target_molecule_id: uuid.UUID
    ) -> list[MoleculeRelationship]:
        return [r for r in self._store if r.target_molecule_id == target_molecule_id]


def _make_mol(name: str = "Test") -> Molecule:
    mol = Molecule.register_undisclosed(
        workspace_id=WS_ID,
        registration_number=RegistrationNumber(value=f"CV-{uuid.uuid4().hex[:5]}"),
        name=name,
        molecule_type=MoleculeType.SMALL_MOLECULE,
        originating_org_id=ORG_ID,
    )
    mol.clear_events()
    return mol


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestListRelationships:
    @pytest.mark.asyncio
    async def test_returns_both_directions(self) -> None:
        mol_repo = FakeMoleculeRepository()
        rel_repo = FakeRelationshipRepository()

        mol_a = _make_mol("A")
        mol_b = _make_mol("B")
        mol_c = _make_mol("C")
        mol_repo.add(mol_a)
        mol_repo.add(mol_b)
        mol_repo.add(mol_c)

        # A -> B (source)
        rel_repo.add(
            MoleculeRelationship.create(
                workspace_id=WS_ID,
                source_molecule_id=mol_a.id,
                target_molecule_id=mol_b.id,
                relationship_type=RelationshipType.SALT_OF,
                created_by=USER_ID,
            )
        )
        # C -> A (target)
        rel_repo.add(
            MoleculeRelationship.create(
                workspace_id=WS_ID,
                source_molecule_id=mol_c.id,
                target_molecule_id=mol_a.id,
                relationship_type=RelationshipType.METABOLITE_OF,
                created_by=USER_ID,
            )
        )

        uc = ListRelationships(FakeUnitOfWork(), mol_repo, rel_repo)
        result = await uc(
            ListRelationshipsQuery(workspace_id=WS_ID, molecule_id=mol_a.id)
        )

        assert isinstance(result, Success)
        rels = result.unwrap()
        assert len(rels) == 2

    @pytest.mark.asyncio
    async def test_empty_results(self) -> None:
        mol_repo = FakeMoleculeRepository()
        rel_repo = FakeRelationshipRepository()
        mol = _make_mol()
        mol_repo.add(mol)

        uc = ListRelationships(FakeUnitOfWork(), mol_repo, rel_repo)
        result = await uc(
            ListRelationshipsQuery(workspace_id=WS_ID, molecule_id=mol.id)
        )

        assert isinstance(result, Success)
        assert result.unwrap() == []

    @pytest.mark.asyncio
    async def test_molecule_not_found(self) -> None:
        mol_repo = FakeMoleculeRepository()
        rel_repo = FakeRelationshipRepository()

        uc = ListRelationships(FakeUnitOfWork(), mol_repo, rel_repo)
        result = await uc(
            ListRelationshipsQuery(workspace_id=WS_ID, molecule_id=uuid.uuid4())
        )

        assert isinstance(result, Failure)
        assert isinstance(result.failure(), NotFoundError)
