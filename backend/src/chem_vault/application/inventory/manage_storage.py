"""StorageLocation CRUD use cases."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Failure, Result, Success

from chem_vault.application.auth import AuthContext, require_editor
from chem_vault.application.shared.command import Command
from chem_vault.application.shared.event_dispatcher import EventDispatcherProtocol
from chem_vault.application.shared.unit_of_work import UnitOfWork
from chem_vault.domain.inventory.enums import StorageLocationType
from chem_vault.domain.inventory.repository import StorageLocationRepository
from chem_vault.domain.inventory.storage_location import StorageLocation
from chem_vault.domain.shared.errors import DomainError, NotFoundError
from chem_vault.domain.shared.value_objects import Barcode


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

        async with self._uow:
            # Resolve parent type if parent_id is provided
            parent_type: StorageLocationType | None = None
            if input.parent_id is not None:
                parent = await self._repo.find_by_id(input.parent_id)
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


class ListStorageLocations:
    def __init__(self, uow: UnitOfWork, repo: StorageLocationRepository) -> None:
        self._uow = uow
        self._repo = repo

    async def __call__(
        self, workspace_id: uuid.UUID
    ) -> Result[list[StorageLocation], DomainError]:
        async with self._uow:
            locations = await self._repo.find_by_workspace(workspace_id)
            return Success(locations)


class GetStorageLocationChildren:
    def __init__(self, uow: UnitOfWork, repo: StorageLocationRepository) -> None:
        self._uow = uow
        self._repo = repo

    async def __call__(
        self, parent_id: uuid.UUID
    ) -> Result[list[StorageLocation], DomainError]:
        async with self._uow:
            children = await self._repo.find_children(parent_id)
            return Success(children)
