"""DeleteRegistrationForm command — remove a registration form template."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Failure, Result, Success

from cellar.application.auth import AuthContext, require_editor, require_same_workspace
from cellar.application.shared.command import Command
from cellar.application.shared.event_dispatcher import EventDispatcherProtocol
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.shared.errors import DomainError, NotFoundError, ValidationError
from cellar.domain.workspace_config.repository import RegistrationFormRepository


@dataclass(frozen=True, kw_only=True)
class DeleteRegistrationFormCommand(Command):
    workspace_id: uuid.UUID
    form_id: uuid.UUID


class DeleteRegistrationForm:
    def __init__(
        self,
        uow: UnitOfWork,
        repo: RegistrationFormRepository,
        dispatcher: EventDispatcherProtocol,
    ) -> None:
        self._uow = uow
        self._repo = repo
        self._dispatcher = dispatcher

    async def __call__(
        self, input: DeleteRegistrationFormCommand, auth: AuthContext | None = None
    ) -> Result[None, DomainError]:
        require_editor(auth)
        require_same_workspace(auth, input.workspace_id)

        async with self._uow:
            form = await self._repo.find_by_id_in_workspace(input.workspace_id, input.form_id)
            if form is None:
                return Failure(NotFoundError("RegistrationForm", str(input.form_id)))

            if form.is_default:
                return Failure(ValidationError("Cannot delete the default registration form"))

            await self._repo.delete(input.workspace_id, input.form_id)
            events = await self._uow.commit()

        await self._dispatcher.dispatch_all(events)
        return Success(None)
