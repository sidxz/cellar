"""DeleteRegistrationForm command — remove a registration form template."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Failure, Result, Success

from chem_vault.application.auth import AuthContext, require_editor
from chem_vault.application.shared.command import Command
from chem_vault.application.shared.event_dispatcher import EventDispatcherProtocol
from chem_vault.application.shared.unit_of_work import UnitOfWork
from chem_vault.domain.shared.errors import DomainError, NotFoundError, ValidationError
from chem_vault.domain.workspace_config.repository import RegistrationFormRepository


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
