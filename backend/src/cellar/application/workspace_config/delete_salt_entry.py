"""DeleteSaltEntry command — remove a salt catalog entry."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Failure, Result, Success

from cellar.application.auth import AuthContext, require_editor, require_same_workspace
from cellar.application.shared.command import Command
from cellar.application.shared.event_dispatcher import EventDispatcherProtocol
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.shared.errors import DomainError, NotFoundError, ValidationError
from cellar.domain.workspace_config.repository import SaltEntryRepository


@dataclass(frozen=True, kw_only=True)
class DeleteSaltEntryCommand(Command):
    workspace_id: uuid.UUID
    entry_id: uuid.UUID


class DeleteSaltEntry:
    def __init__(
        self,
        uow: UnitOfWork,
        repo: SaltEntryRepository,
        dispatcher: EventDispatcherProtocol,
    ) -> None:
        self._uow = uow
        self._repo = repo
        self._dispatcher = dispatcher

    async def __call__(
        self, input: DeleteSaltEntryCommand, auth: AuthContext | None = None
    ) -> Result[None, DomainError]:
        require_editor(auth)
        require_same_workspace(auth, input.workspace_id)

        async with self._uow:
            entry = await self._repo.find_by_id_in_workspace(input.workspace_id, input.entry_id)
            if entry is None:
                return Failure(NotFoundError("SaltEntry", str(input.entry_id)))

            if entry.is_default:
                return Failure(ValidationError("Cannot delete default salt entries"))

            await self._repo.delete(input.workspace_id, input.entry_id)
            events = await self._uow.commit()

        await self._dispatcher.dispatch_all(events)
        return Success(None)
