"""DeleteTarget command — remove a target entity."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Failure, Result, Success

from cellar.application.auth import AuthContext, require_admin
from cellar.application.shared.command import Command
from cellar.application.shared.event_dispatcher import EventDispatcherProtocol
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.screening_assay.repository import TargetRepository
from cellar.domain.shared.errors import DomainError, NotFoundError


@dataclass(frozen=True, kw_only=True)
class DeleteTargetCommand(Command):
    workspace_id: uuid.UUID
    target_id: uuid.UUID


class DeleteTarget:
    def __init__(
        self,
        uow: UnitOfWork,
        repo: TargetRepository,
        dispatcher: EventDispatcherProtocol,
    ) -> None:
        self._uow = uow
        self._repo = repo
        self._dispatcher = dispatcher

    async def __call__(
        self, input: DeleteTargetCommand, auth: AuthContext | None = None
    ) -> Result[None, DomainError]:
        require_admin(auth)

        async with self._uow:
            target = await self._repo.find_by_id_in_workspace(input.workspace_id, input.target_id)
            if target is None:
                return Failure(NotFoundError("Target", str(input.target_id)))

            await self._repo.delete(input.workspace_id, input.target_id)
            events = await self._uow.commit()

        await self._dispatcher.dispatch_all(events)
        return Success(None)
