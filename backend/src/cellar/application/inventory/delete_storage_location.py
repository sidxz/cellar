"""DeleteStorageLocation command — remove a storage location entity."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Failure, Result, Success

from cellar.application.auth import AuthContext, require_admin
from cellar.application.shared.command import Command
from cellar.application.shared.event_dispatcher import EventDispatcherProtocol
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.inventory.repository import (
    SampleRepository,
    StorageLocationRepository,
)
from cellar.domain.shared.errors import ConflictError, DomainError, NotFoundError


@dataclass(frozen=True, kw_only=True)
class DeleteStorageLocationCommand(Command):
    workspace_id: uuid.UUID
    location_id: uuid.UUID


class DeleteStorageLocation:
    def __init__(
        self,
        uow: UnitOfWork,
        repo: StorageLocationRepository,
        sample_repo: SampleRepository,
        dispatcher: EventDispatcherProtocol,
    ) -> None:
        self._uow = uow
        self._repo = repo
        self._sample_repo = sample_repo
        self._dispatcher = dispatcher

    async def __call__(
        self, input: DeleteStorageLocationCommand, auth: AuthContext | None = None
    ) -> Result[None, DomainError]:
        require_admin(auth)

        async with self._uow:
            loc = await self._repo.find_by_id_in_workspace(input.workspace_id, input.location_id)
            if loc is None:
                return Failure(NotFoundError("StorageLocation", str(input.location_id)))

            # Prevent deletion if location has children
            children = await self._repo.find_children(input.workspace_id, input.location_id)
            if children:
                return Failure(
                    ConflictError(
                        f"Cannot delete storage location '{loc.name}': "
                        f"it has {len(children)} child location(s)"
                    )
                )

            # Prevent deletion if location has samples
            samples = await self._sample_repo.find_by_location(
                input.workspace_id, input.location_id
            )
            if samples:
                return Failure(
                    ConflictError(
                        f"Cannot delete storage location '{loc.name}': "
                        f"it has {len(samples)} sample(s)"
                    )
                )

            await self._repo.delete(input.workspace_id, input.location_id)
            events = await self._uow.commit()

        await self._dispatcher.dispatch_all(events)
        return Success(None)
