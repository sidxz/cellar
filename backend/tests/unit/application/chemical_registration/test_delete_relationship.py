"""Tests for DeleteRelationship command use case."""

from __future__ import annotations

import uuid
from types import TracebackType
from typing import Self

import pytest
from returns.result import Failure, Success

from chem_vault.application.chemical_registration.delete_relationship import (
    DeleteRelationship,
    DeleteRelationshipCommand,
)
from chem_vault.domain.chemical_registration.enums import RelationshipType
from chem_vault.domain.chemical_registration.molecule_relationship import MoleculeRelationship
from chem_vault.domain.shared.errors import NotFoundError
from chem_vault.domain.shared.events import DomainEvent
from tests.fakes.fake_auth import FakeAuth

# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------

WS_ID = uuid.uuid4()
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


class FakeRelationshipRepository:
    def __init__(self) -> None:
        self._store: dict[uuid.UUID, MoleculeRelationship] = {}
        self.deleted_ids: list[uuid.UUID] = []

    def add(self, rel: MoleculeRelationship) -> None:
        self._store[rel.id] = rel

    async def find_by_id(self, id: uuid.UUID) -> MoleculeRelationship | None:
        return self._store.get(id)

    async def delete(self, id: uuid.UUID) -> None:
        self._store.pop(id, None)
        self.deleted_ids.append(id)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestDeleteRelationship:
    @pytest.mark.asyncio
    async def test_happy_path(self) -> None:
        uow = FakeUnitOfWork()
        rel_repo = FakeRelationshipRepository()
        dispatcher = FakeEventDispatcher()

        rel = MoleculeRelationship.create(
            workspace_id=WS_ID,
            source_molecule_id=uuid.uuid4(),
            target_molecule_id=uuid.uuid4(),
            relationship_type=RelationshipType.ANALOG_OF,
            created_by=USER_ID,
        )
        rel_repo.add(rel)

        uc = DeleteRelationship(uow, rel_repo, dispatcher)
        result = await uc(
            DeleteRelationshipCommand(
                workspace_id=WS_ID,
                relationship_id=rel.id,
            ),
            auth=FakeAuth(),
        )

        assert isinstance(result, Success)
        assert rel.id in rel_repo.deleted_ids
        assert uow.committed

    @pytest.mark.asyncio
    async def test_not_found(self) -> None:
        uow = FakeUnitOfWork()
        rel_repo = FakeRelationshipRepository()
        dispatcher = FakeEventDispatcher()

        uc = DeleteRelationship(uow, rel_repo, dispatcher)
        result = await uc(
            DeleteRelationshipCommand(
                workspace_id=WS_ID,
                relationship_id=uuid.uuid4(),
            ),
            auth=FakeAuth(),
        )

        assert isinstance(result, Failure)
        assert isinstance(result.failure(), NotFoundError)

    @pytest.mark.asyncio
    async def test_wrong_workspace(self) -> None:
        uow = FakeUnitOfWork()
        rel_repo = FakeRelationshipRepository()
        dispatcher = FakeEventDispatcher()

        rel = MoleculeRelationship.create(
            workspace_id=WS_ID,
            source_molecule_id=uuid.uuid4(),
            target_molecule_id=uuid.uuid4(),
            relationship_type=RelationshipType.ANALOG_OF,
            created_by=USER_ID,
        )
        rel_repo.add(rel)

        uc = DeleteRelationship(uow, rel_repo, dispatcher)
        result = await uc(
            DeleteRelationshipCommand(
                workspace_id=uuid.uuid4(),  # different workspace
                relationship_id=rel.id,
            ),
            auth=FakeAuth(),
        )

        assert isinstance(result, Failure)
        assert isinstance(result.failure(), NotFoundError)
