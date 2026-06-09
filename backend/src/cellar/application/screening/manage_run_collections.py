"""Run-collection association use cases — attach / detach a collection on a run.

Mirrors ``manage_run_targets``: collections are an M2M association (not aggregate
state), so the lock guard uses a column-only query, the audit event is
constructed here, and there is no version bump on idempotent edits. Coverage is
computed live elsewhere (``coverage_query``); these use cases only manage links.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Failure, Result, Success

from cellar.application.auth import AuthContext, require_editor, require_same_workspace
from cellar.application.shared.command import Command
from cellar.application.shared.event_dispatcher import EventDispatcherProtocol
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.screening_assay.events import (
    RunCollectionAdded,
    RunCollectionRemoved,
)
from cellar.domain.screening_assay.repository import CollectionLinkResult, RunRepository
from cellar.domain.shared.errors import ConflictError, DomainError, NotFoundError


@dataclass(frozen=True, kw_only=True)
class AddRunCollectionCommand(Command):
    workspace_id: uuid.UUID
    run_id: uuid.UUID
    collection_id: uuid.UUID


@dataclass(frozen=True, kw_only=True)
class RemoveRunCollectionCommand(Command):
    workspace_id: uuid.UUID
    run_id: uuid.UUID
    collection_id: uuid.UUID


class AddRunCollection:
    """Attach a collection to a run (idempotent). Blocked when the run is locked."""

    def __init__(
        self,
        uow: UnitOfWork,
        repo: RunRepository,
        dispatcher: EventDispatcherProtocol,
    ) -> None:
        self._uow = uow
        self._repo = repo
        self._dispatcher = dispatcher

    async def __call__(
        self, input: AddRunCollectionCommand, auth: AuthContext | None = None
    ) -> Result[None, DomainError]:
        require_editor(auth)
        require_same_workspace(auth, input.workspace_id)
        async with self._uow:
            is_locked = await self._repo.find_lock_state(input.workspace_id, input.run_id)
            if is_locked is None:
                return Failure(NotFoundError("Run", str(input.run_id)))
            if is_locked:
                return Failure(ConflictError("Cannot modify a locked run — unlock it first"))
            link = await self._repo.add_collection(
                input.workspace_id, input.run_id, input.collection_id
            )
            if link is CollectionLinkResult.COLLECTION_NOT_FOUND:
                return Failure(NotFoundError("Collection", str(input.collection_id)))
            if link is CollectionLinkResult.OWNER_NOT_FOUND:
                return Failure(NotFoundError("Run", str(input.run_id)))
            events = await self._uow.commit()

        if link is CollectionLinkResult.ADDED:
            events.append(
                RunCollectionAdded(
                    aggregate_id=input.run_id,
                    aggregate_type="Run",
                    workspace_id=input.workspace_id,
                    collection_id=input.collection_id,
                    user_id=auth.user_id if auth else None,
                )
            )
        await self._dispatcher.dispatch_all(events)
        return Success(None)


class RemoveRunCollection:
    """Detach a collection from a run. Blocked when the run is locked."""

    def __init__(
        self,
        uow: UnitOfWork,
        repo: RunRepository,
        dispatcher: EventDispatcherProtocol,
    ) -> None:
        self._uow = uow
        self._repo = repo
        self._dispatcher = dispatcher

    async def __call__(
        self, input: RemoveRunCollectionCommand, auth: AuthContext | None = None
    ) -> Result[None, DomainError]:
        require_editor(auth)
        require_same_workspace(auth, input.workspace_id)
        async with self._uow:
            is_locked = await self._repo.find_lock_state(input.workspace_id, input.run_id)
            if is_locked is None:
                return Failure(NotFoundError("Run", str(input.run_id)))
            if is_locked:
                return Failure(ConflictError("Cannot modify a locked run — unlock it first"))
            removed = await self._repo.remove_collection(
                input.workspace_id, input.run_id, input.collection_id
            )
            events = await self._uow.commit()

        if removed:
            events.append(
                RunCollectionRemoved(
                    aggregate_id=input.run_id,
                    aggregate_type="Run",
                    workspace_id=input.workspace_id,
                    collection_id=input.collection_id,
                    user_id=auth.user_id if auth else None,
                )
            )
        await self._dispatcher.dispatch_all(events)
        return Success(None)
