"""Tests for CreateRelationship command use case."""

from __future__ import annotations

import uuid
from types import TracebackType
from typing import Self

import pytest
from returns.result import Failure, Success

from cellar.application.chemical_registration.create_relationship import (
    CreateRelationship,
    CreateRelationshipCommand,
)
from cellar.domain.chemical_registration.enums import MoleculeType, RelationshipType
from cellar.domain.chemical_registration.molecule import Molecule
from cellar.domain.chemical_registration.molecule_relationship import MoleculeRelationship
from cellar.domain.shared.errors import NotFoundError, ValidationError
from cellar.domain.shared.events import DomainEvent
from cellar.domain.shared.value_objects import RegistrationNumber
from tests.fakes.fake_auth import FakeAuth

# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------

WS_ID = uuid.uuid4()
ORG_ID = uuid.uuid4()
USER_ID = uuid.uuid4()


class FakeUnitOfWork:
    def __init__(self) -> None:
        self.committed = False

    async def commit(self) -> list[DomainEvent]:
        self.committed = True
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


class FakeEventDispatcher:
    def __init__(self) -> None:
        self.dispatched: list[DomainEvent] = []

    async def dispatch_all(self, events: list[DomainEvent]) -> None:
        self.dispatched.extend(events)


class FakeMoleculeRepository:
    def __init__(self) -> None:
        self._store: dict[uuid.UUID, Molecule] = {}

    def add(self, mol: Molecule) -> None:
        self._store[mol.id] = mol

    async def find_by_id(self, id: uuid.UUID) -> Molecule | None:
        return self._store.get(id)

    async def find_by_id_in_workspace(
        self, workspace_id: uuid.UUID, id: uuid.UUID
    ) -> Molecule | None:
        entity = self._store.get(id)
        if entity is not None and entity.workspace_id != workspace_id:
            return None
        return entity


class FakeRelationshipRepository:
    def __init__(self) -> None:
        self.saved: list[MoleculeRelationship] = []

    async def save(self, entity: MoleculeRelationship) -> None:
        self.saved.append(entity)


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


class TestCreateRelationship:
    @pytest.mark.asyncio
    async def test_happy_path(self) -> None:
        uow = FakeUnitOfWork()
        mol_repo = FakeMoleculeRepository()
        rel_repo = FakeRelationshipRepository()
        dispatcher = FakeEventDispatcher()

        source = _make_mol("Source")
        target = _make_mol("Target")
        mol_repo.add(source)
        mol_repo.add(target)

        uc = CreateRelationship(uow, mol_repo, rel_repo, dispatcher)
        result = await uc(
            CreateRelationshipCommand(
                workspace_id=WS_ID,
                source_molecule_id=source.id,
                target_molecule_id=target.id,
                relationship_type="salt_of",
                notes="hydrochloride salt",
                created_by=USER_ID,
            ),
            auth=FakeAuth(workspace_id=WS_ID),
        )

        assert isinstance(result, Success)
        rel = result.unwrap()
        assert rel.source_molecule_id == source.id
        assert rel.target_molecule_id == target.id
        assert rel.relationship_type == RelationshipType.SALT_OF
        assert rel.notes == "hydrochloride salt"
        assert len(rel_repo.saved) == 1
        assert uow.committed

    @pytest.mark.asyncio
    async def test_source_not_found(self) -> None:
        uow = FakeUnitOfWork()
        mol_repo = FakeMoleculeRepository()
        rel_repo = FakeRelationshipRepository()
        dispatcher = FakeEventDispatcher()

        target = _make_mol("Target")
        mol_repo.add(target)

        uc = CreateRelationship(uow, mol_repo, rel_repo, dispatcher)
        result = await uc(
            CreateRelationshipCommand(
                workspace_id=WS_ID,
                source_molecule_id=uuid.uuid4(),
                target_molecule_id=target.id,
                relationship_type="salt_of",
                created_by=USER_ID,
            ),
            auth=FakeAuth(workspace_id=WS_ID),
        )

        assert isinstance(result, Failure)
        assert isinstance(result.failure(), NotFoundError)

    @pytest.mark.asyncio
    async def test_target_not_found(self) -> None:
        uow = FakeUnitOfWork()
        mol_repo = FakeMoleculeRepository()
        rel_repo = FakeRelationshipRepository()
        dispatcher = FakeEventDispatcher()

        source = _make_mol("Source")
        mol_repo.add(source)

        uc = CreateRelationship(uow, mol_repo, rel_repo, dispatcher)
        result = await uc(
            CreateRelationshipCommand(
                workspace_id=WS_ID,
                source_molecule_id=source.id,
                target_molecule_id=uuid.uuid4(),
                relationship_type="salt_of",
                created_by=USER_ID,
            ),
            auth=FakeAuth(workspace_id=WS_ID),
        )

        assert isinstance(result, Failure)
        assert isinstance(result.failure(), NotFoundError)

    @pytest.mark.asyncio
    async def test_self_relationship_raises(self) -> None:
        uow = FakeUnitOfWork()
        mol_repo = FakeMoleculeRepository()
        rel_repo = FakeRelationshipRepository()
        dispatcher = FakeEventDispatcher()

        mol = _make_mol()
        mol_repo.add(mol)

        uc = CreateRelationship(uow, mol_repo, rel_repo, dispatcher)
        # Self-relationship triggers ValidationError from domain
        with pytest.raises(ValidationError, match="itself"):
            await uc(
                CreateRelationshipCommand(
                    workspace_id=WS_ID,
                    source_molecule_id=mol.id,
                    target_molecule_id=mol.id,
                    relationship_type="analog_of",
                    created_by=USER_ID,
                ),
                auth=FakeAuth(workspace_id=WS_ID),
            )

    @pytest.mark.asyncio
    async def test_invalid_relationship_type(self) -> None:
        uow = FakeUnitOfWork()
        mol_repo = FakeMoleculeRepository()
        rel_repo = FakeRelationshipRepository()
        dispatcher = FakeEventDispatcher()

        source = _make_mol("Source")
        target = _make_mol("Target")
        mol_repo.add(source)
        mol_repo.add(target)

        uc = CreateRelationship(uow, mol_repo, rel_repo, dispatcher)
        result = await uc(
            CreateRelationshipCommand(
                workspace_id=WS_ID,
                source_molecule_id=source.id,
                target_molecule_id=target.id,
                relationship_type="invalid_type",
                created_by=USER_ID,
            ),
            auth=FakeAuth(workspace_id=WS_ID),
        )

        assert isinstance(result, Failure)
        assert isinstance(result.failure(), ValidationError)

    @pytest.mark.asyncio
    async def test_wrong_workspace(self) -> None:
        uow = FakeUnitOfWork()
        mol_repo = FakeMoleculeRepository()
        rel_repo = FakeRelationshipRepository()
        dispatcher = FakeEventDispatcher()

        source = _make_mol("Source")
        target = _make_mol("Target")
        mol_repo.add(source)
        mol_repo.add(target)

        uc = CreateRelationship(uow, mol_repo, rel_repo, dispatcher)
        # The workspace guard rejects a command whose workspace differs from
        # the caller's, raising NotFoundError to avoid leaking entity existence.
        with pytest.raises(NotFoundError):
            await uc(
                CreateRelationshipCommand(
                    workspace_id=uuid.uuid4(),  # different workspace
                    source_molecule_id=source.id,
                    target_molecule_id=target.id,
                    relationship_type="salt_of",
                    created_by=USER_ID,
                ),
                auth=FakeAuth(workspace_id=WS_ID),
            )
