"""Batch identifier CRUD -- add, remove, list external identifiers on a batch."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Failure, Result, Success

from cellar.application.auth import AuthContext, require_editor, require_workspace_role
from cellar.application.shared.command import Command
from cellar.application.shared.event_dispatcher import EventDispatcherProtocol
from cellar.application.shared.query import Query
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.inventory.batch import Batch
from cellar.domain.inventory.batch_identifier import BatchIdentifier
from cellar.domain.inventory.repository import BatchRepository
from cellar.domain.shared.errors import ConflictError, DomainError, NotFoundError, ValidationError

# ---------------------------------------------------------------------------
# Commands / Queries
# ---------------------------------------------------------------------------


@dataclass(frozen=True, kw_only=True)
class AddBatchIdentifierCommand(Command):
    workspace_id: uuid.UUID
    batch_id: uuid.UUID
    identifier: str
    identifier_type: str
    source: str
    registered_by: uuid.UUID


@dataclass(frozen=True, kw_only=True)
class RemoveBatchIdentifierCommand(Command):
    workspace_id: uuid.UUID
    batch_id: uuid.UUID
    identifier_id: uuid.UUID


@dataclass(frozen=True, kw_only=True)
class ListBatchIdentifiersQuery(Query):
    workspace_id: uuid.UUID
    batch_id: uuid.UUID


# ---------------------------------------------------------------------------
# Use Cases
# ---------------------------------------------------------------------------


class AddBatchIdentifier:
    """Add an external identifier to a batch."""

    def __init__(
        self,
        uow: UnitOfWork,
        repo: BatchRepository,
        dispatcher: EventDispatcherProtocol,
    ) -> None:
        self._uow = uow
        self._repo = repo
        self._dispatcher = dispatcher

    async def __call__(
        self,
        input: AddBatchIdentifierCommand,
        auth: AuthContext | None = None,
    ) -> Result[Batch, DomainError]:
        require_editor(auth)

        async with self._uow:
            batch = await self._repo.find_by_id_in_workspace(input.workspace_id, input.batch_id)
            if batch is None:
                return Failure(NotFoundError("Batch", str(input.batch_id)))

            # Workspace-unique check: identifier must not exist on another batch
            existing = await self._repo.find_by_external_identifier(
                input.workspace_id, input.identifier
            )
            if existing is not None and existing.id != batch.id:
                return Failure(
                    ConflictError(
                        f"Identifier '{input.identifier}' is already assigned to "
                        f"batch '{existing.batch_number.value}'"
                    )
                )

            try:
                ident = BatchIdentifier.create(
                    batch_id=batch.id,
                    identifier=input.identifier,
                    identifier_type=input.identifier_type,
                    source=input.source,
                    registered_by=input.registered_by,
                )
                batch.add_identifier(ident)
            except (ValidationError, ValueError) as exc:
                if isinstance(exc, ValueError):
                    return Failure(ValidationError(str(exc)))
                return Failure(exc)

            await self._repo.save(batch)
            events = await self._uow.commit()

        await self._dispatcher.dispatch_all(events)
        return Success(batch)


class RemoveBatchIdentifier:
    """Remove an identifier from a batch by ID."""

    def __init__(
        self,
        uow: UnitOfWork,
        repo: BatchRepository,
        dispatcher: EventDispatcherProtocol,
    ) -> None:
        self._uow = uow
        self._repo = repo
        self._dispatcher = dispatcher

    async def __call__(
        self,
        input: RemoveBatchIdentifierCommand,
        auth: AuthContext | None = None,
    ) -> Result[None, DomainError]:
        require_editor(auth)

        async with self._uow:
            batch = await self._repo.find_by_id_in_workspace(input.workspace_id, input.batch_id)
            if batch is None:
                return Failure(NotFoundError("Batch", str(input.batch_id)))

            try:
                batch.remove_identifier(input.identifier_id)
            except ValidationError as exc:
                return Failure(exc)

            await self._repo.save(batch)
            events = await self._uow.commit()

        await self._dispatcher.dispatch_all(events)
        return Success(None)


class ListBatchIdentifiers:
    """List all identifiers on a batch (read-only)."""

    def __init__(self, uow: UnitOfWork, repo: BatchRepository) -> None:
        self._uow = uow
        self._repo = repo

    async def __call__(
        self,
        input: ListBatchIdentifiersQuery,
        auth: AuthContext | None = None,
    ) -> Result[list[BatchIdentifier], DomainError]:
        require_workspace_role(auth, "viewer")
        async with self._uow:
            batch = await self._repo.find_by_id_in_workspace(input.workspace_id, input.batch_id)
            if batch is None:
                return Failure(NotFoundError("Batch", str(input.batch_id)))
            return Success(batch.identifiers)
