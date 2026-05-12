"""UpdateStorageLocation command — partial update of an existing storage location."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from returns.result import Failure, Result, Success

from cellar.application.auth import AuthContext, require_editor
from cellar.application.shared.command import Command
from cellar.application.shared.event_dispatcher import EventDispatcherProtocol
from cellar.application.shared.sentinel import UNSET
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.inventory.repository import StorageLocationRepository
from cellar.domain.inventory.storage_location import StorageLocation
from cellar.domain.shared.errors import DomainError, NotFoundError
from cellar.domain.shared.value_objects import Barcode


@dataclass(frozen=True, kw_only=True)
class UpdateStorageLocationCommand(Command):
    workspace_id: uuid.UUID
    location_id: uuid.UUID
    name: str | None = None
    barcode: str | None | object = UNSET
    temperature: str | None | object = UNSET
    rows: int | None | object = UNSET
    columns: int | None | object = UNSET
    capacity: int | None | object = UNSET


class UpdateStorageLocation:
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
        self, input: UpdateStorageLocationCommand, auth: AuthContext | None = None
    ) -> Result[StorageLocation, DomainError]:
        require_editor(auth)

        async with self._uow:
            loc = await self._repo.find_by_id_in_workspace(input.workspace_id, input.location_id)
            if loc is None:
                return Failure(NotFoundError("StorageLocation", str(input.location_id)))

            fields: dict[str, Any] = {}
            if input.name is not None:
                fields["name"] = input.name
            if input.barcode is not UNSET:
                fields["barcode"] = Barcode(value=input.barcode) if input.barcode else None
            if input.temperature is not UNSET:
                fields["temperature"] = input.temperature
            if input.rows is not UNSET:
                fields["rows"] = input.rows
            if input.columns is not UNSET:
                fields["columns"] = input.columns
            if input.capacity is not UNSET:
                fields["capacity"] = input.capacity

            if fields:
                loc.update(**fields)
            await self._repo.save(loc)
            events = await self._uow.commit()

        await self._dispatcher.dispatch_all(events)
        return Success(loc)
