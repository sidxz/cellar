"""DeleteProtocolForm command — remove a protocol form template."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Failure, Result, Success

from chem_vault.application.auth import AuthContext, require_admin
from chem_vault.application.shared.command import Command
from chem_vault.application.shared.event_dispatcher import EventDispatcherProtocol
from chem_vault.application.shared.unit_of_work import UnitOfWork
from chem_vault.domain.shared.errors import DomainError, NotFoundError
from chem_vault.domain.workspace_config.repository import ProtocolFormRepository


@dataclass(frozen=True, kw_only=True)
class DeleteProtocolFormCommand(Command):
    workspace_id: uuid.UUID
    form_id: uuid.UUID


class DeleteProtocolForm:
    def __init__(
        self,
        uow: UnitOfWork,
        repo: ProtocolFormRepository,
        dispatcher: EventDispatcherProtocol,
    ) -> None:
        self._uow = uow
        self._repo = repo
        self._dispatcher = dispatcher

    async def __call__(
        self, input: DeleteProtocolFormCommand, auth: AuthContext | None = None
    ) -> Result[None, DomainError]:
        require_admin(auth)

        async with self._uow:
            form = await self._repo.find_by_id_in_workspace(input.workspace_id, input.form_id)
            if form is None:
                return Failure(NotFoundError("ProtocolForm", str(input.form_id)))

            await self._repo.delete(input.workspace_id, input.form_id)
            events = await self._uow.commit()
            await self._dispatcher.dispatch_all(events)
            return Success(None)
