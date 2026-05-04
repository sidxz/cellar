"""Collection membership use cases — add, remove, and list molecules."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from returns.result import Failure, Result, Success

from chem_vault.application.auth import AuthContext, require_editor
from chem_vault.application.shared.command import Command
from chem_vault.application.shared.event_dispatcher import EventDispatcherProtocol
from chem_vault.application.shared.molecule_resolver import (
    MoleculeReference,
    MoleculeResolver,
    UnresolvedMolecule,
)
from chem_vault.application.shared.query import Query
from chem_vault.application.shared.unit_of_work import UnitOfWork
from chem_vault.domain.research_organization.events import CollectionMembersChanged
from chem_vault.domain.research_organization.repository import CollectionRepository
from chem_vault.domain.shared.errors import DomainError, NotFoundError


# ---------------------------------------------------------------------------
# Result DTO
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MembershipResult:
    """Outcome of an add-molecules operation."""

    added: list[uuid.UUID]
    already_present: int
    unresolved: list[UnresolvedMolecule]


# ---------------------------------------------------------------------------
# AddMoleculesToCollection
# ---------------------------------------------------------------------------


@dataclass(frozen=True, kw_only=True)
class AddMoleculesToCollectionCommand(Command):
    workspace_id: uuid.UUID
    collection_id: uuid.UUID
    refs: list[MoleculeReference]
    added_by: uuid.UUID


class AddMoleculesToCollection:
    def __init__(
        self,
        uow: UnitOfWork,
        collection_repo: CollectionRepository,
        resolver: MoleculeResolver,
        dispatcher: EventDispatcherProtocol,
    ) -> None:
        self._uow = uow
        self._collection_repo = collection_repo
        self._resolver = resolver
        self._dispatcher = dispatcher

    async def __call__(
        self,
        input: AddMoleculesToCollectionCommand,
        auth: AuthContext | None = None,
    ) -> Result[MembershipResult, DomainError]:
        require_editor(auth)

        async with self._uow:
            collection = await self._collection_repo.find_by_id_in_workspace(input.workspace_id, input.collection_id)
            if collection is None:
                return Failure(
                    NotFoundError("Collection", str(input.collection_id))
                )

            resolved, unresolved = await self._resolver.resolve(
                input.workspace_id, input.refs
            )

            if not resolved:
                # Nothing to add — return result with unresolved only
                return Success(
                    MembershipResult(added=[], already_present=0, unresolved=unresolved)
                )

            molecule_ids = [r.molecule_id for r in resolved]
            added_count = await self._collection_repo.add_molecules(
                input.workspace_id, input.collection_id, molecule_ids
            )

            already_present = len(molecule_ids) - added_count
            added_ids = molecule_ids[:added_count] if added_count > 0 else []

            if added_count > 0:
                collection.register_event(
                    CollectionMembersChanged(
                        aggregate_id=collection.id,
                        aggregate_type="Collection",
                        workspace_id=collection.workspace_id,
                        added_ids=added_ids,
                        removed_ids=[],
                    )
                )

            events = await self._uow.commit()

        await self._dispatcher.dispatch_all(events)
        return Success(
            MembershipResult(
                added=added_ids,
                already_present=already_present,
                unresolved=unresolved,
            )
        )


# ---------------------------------------------------------------------------
# RemoveMoleculesFromCollection
# ---------------------------------------------------------------------------


@dataclass(frozen=True, kw_only=True)
class RemoveMoleculesFromCollectionCommand(Command):
    workspace_id: uuid.UUID
    collection_id: uuid.UUID
    molecule_ids: list[uuid.UUID]


class RemoveMoleculesFromCollection:
    def __init__(
        self,
        uow: UnitOfWork,
        collection_repo: CollectionRepository,
        dispatcher: EventDispatcherProtocol,
    ) -> None:
        self._uow = uow
        self._collection_repo = collection_repo
        self._dispatcher = dispatcher

    async def __call__(
        self,
        input: RemoveMoleculesFromCollectionCommand,
        auth: AuthContext | None = None,
    ) -> Result[int, DomainError]:
        require_editor(auth)

        async with self._uow:
            collection = await self._collection_repo.find_by_id_in_workspace(input.workspace_id, input.collection_id)
            if collection is None:
                return Failure(
                    NotFoundError("Collection", str(input.collection_id))
                )

            removed_count = await self._collection_repo.remove_molecules(
                input.workspace_id, input.collection_id, input.molecule_ids
            )

            if removed_count > 0:
                collection.register_event(
                    CollectionMembersChanged(
                        aggregate_id=collection.id,
                        aggregate_type="Collection",
                        workspace_id=collection.workspace_id,
                        added_ids=[],
                        removed_ids=input.molecule_ids[:removed_count],
                    )
                )

            events = await self._uow.commit()

        await self._dispatcher.dispatch_all(events)
        return Success(removed_count)


# ---------------------------------------------------------------------------
# ListCollectionMolecules
# ---------------------------------------------------------------------------


@dataclass(frozen=True, kw_only=True)
class ListCollectionMoleculesQuery(Query):
    workspace_id: uuid.UUID
    collection_id: uuid.UUID
    offset: int = 0
    limit: int = 100


class ListCollectionMolecules:
    def __init__(
        self,
        uow: UnitOfWork,
        collection_repo: CollectionRepository,
    ) -> None:
        self._uow = uow
        self._collection_repo = collection_repo

    async def __call__(
        self, input: ListCollectionMoleculesQuery
    ) -> Result[list[uuid.UUID], DomainError]:
        async with self._uow:
            collection = await self._collection_repo.find_by_id_in_workspace(input.workspace_id, input.collection_id)
            if collection is None:
                return Failure(
                    NotFoundError("Collection", str(input.collection_id))
                )

            molecule_ids = await self._collection_repo.get_molecule_ids(
                input.workspace_id, input.collection_id, offset=input.offset, limit=input.limit
            )
            return Success(molecule_ids)
