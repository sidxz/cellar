"""StorageLocation CRUD use cases."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Failure, Result, Success

from cellar.application.auth import (
    AuthContext,
    require_editor,
    require_same_workspace,
    require_workspace_role,
)
from cellar.application.shared.command import Command
from cellar.application.shared.event_dispatcher import EventDispatcherProtocol
from cellar.application.shared.pagination import PageResult
from cellar.application.shared.query import Query
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.inventory.enums import StorageLocationType
from cellar.domain.inventory.repository import StorageLocationRepository
from cellar.domain.inventory.storage_location import StorageLocation
from cellar.domain.shared.errors import DomainError, NotFoundError
from cellar.domain.shared.value_objects import Barcode


@dataclass(frozen=True, kw_only=True)
class CreateStorageLocationCommand(Command):
    workspace_id: uuid.UUID
    name: str
    type: str
    parent_id: uuid.UUID | None = None
    barcode: str | None = None
    temperature: str | None = None
    rows: int | None = None
    columns: int | None = None
    capacity: int | None = None


class CreateStorageLocation:
    def __init__(
        self,
        uow: UnitOfWork,
        repo: StorageLocationRepository,
        dispatcher: EventDispatcherProtocol,
    ) -> None:
        self._uow = uow
        self._repo = repo
        self._dispatcher = dispatcher

    async def __call__(
        self, input: CreateStorageLocationCommand, auth: AuthContext | None = None
    ) -> Result[StorageLocation, DomainError]:
        require_editor(auth)
        require_same_workspace(auth, input.workspace_id)

        async with self._uow:
            parent_type: StorageLocationType | None = None
            if input.parent_id is not None:
                parent = await self._repo.find_by_id_in_workspace(
                    input.workspace_id, input.parent_id
                )
                if parent is None:
                    return Failure(NotFoundError("Parent StorageLocation"))
                parent_type = parent.type

            loc = StorageLocation.create(
                workspace_id=input.workspace_id,
                name=input.name,
                type=StorageLocationType(input.type),
                parent_id=input.parent_id,
                parent_type=parent_type,
                barcode=Barcode(value=input.barcode) if input.barcode else None,
                temperature=input.temperature,
                rows=input.rows,
                columns=input.columns,
                capacity=input.capacity,
            )

            await self._repo.save(loc)
            events = await self._uow.commit()

        await self._dispatcher.dispatch_all(events)
        return Success(loc)


@dataclass(frozen=True, kw_only=True)
class ListStorageLocationsQuery(Query):
    workspace_id: uuid.UUID
    cursor_id: uuid.UUID | None = None
    limit: int | None = None


@dataclass(frozen=True, kw_only=True)
class GetStorageLocationChildrenQuery(Query):
    workspace_id: uuid.UUID
    parent_id: uuid.UUID


class ListStorageLocations:
    def __init__(self, uow: UnitOfWork, repo: StorageLocationRepository) -> None:
        self._uow = uow
        self._repo = repo

    async def __call__(
        self, input: ListStorageLocationsQuery, auth: AuthContext | None = None
    ) -> Result[PageResult[StorageLocation], DomainError]:
        require_workspace_role(auth, "viewer")
        require_same_workspace(auth, input.workspace_id)
        async with self._uow:
            effective_limit = input.limit
            fetch_limit = effective_limit + 1 if effective_limit is not None else None
            locations = await self._repo.find_by_workspace(
                input.workspace_id,
                cursor_id=input.cursor_id,
                limit=fetch_limit,
            )

            next_cursor: str | None = None
            if effective_limit is not None and len(locations) > effective_limit:
                locations = locations[:effective_limit]
                next_cursor = str(locations[-1].id)

            return Success(PageResult(items=locations, next_cursor=next_cursor))


class GetStorageLocationChildren:
    def __init__(self, uow: UnitOfWork, repo: StorageLocationRepository) -> None:
        self._uow = uow
        self._repo = repo

    async def __call__(
        self, input: GetStorageLocationChildrenQuery, auth: AuthContext | None = None
    ) -> Result[list[StorageLocation], DomainError]:
        require_workspace_role(auth, "viewer")
        require_same_workspace(auth, input.workspace_id)
        async with self._uow:
            children = await self._repo.find_children(input.workspace_id, input.parent_id)
            return Success(children)


class ListStorageLocationsWithCounts:
    """Return all storage locations with available-sample counts."""

    def __init__(self, uow: UnitOfWork, repo: StorageLocationRepository) -> None:
        self._uow = uow
        self._repo = repo

    async def __call__(
        self, input: ListStorageLocationsQuery, auth: AuthContext | None = None
    ) -> Result[list[dict], DomainError]:
        require_workspace_role(auth, "viewer")
        require_same_workspace(auth, input.workspace_id)
        async with self._uow:
            rows = await self._repo.find_by_workspace_with_counts(input.workspace_id)
            return Success(rows)
