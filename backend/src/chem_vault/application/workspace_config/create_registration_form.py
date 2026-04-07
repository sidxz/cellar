"""CreateRegistrationForm command — create a new registration form template."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from returns.result import Failure, Result, Success

from chem_vault.application.auth import AuthContext, require_editor
from chem_vault.application.shared.command import Command
from chem_vault.application.shared.event_dispatcher import EventDispatcherProtocol
from chem_vault.application.shared.unit_of_work import UnitOfWork
from chem_vault.domain.shared.errors import ConflictError, DomainError
from chem_vault.domain.workspace_config.enums import FieldTarget
from chem_vault.domain.workspace_config.registration_form import FieldOverride, RegistrationForm
from chem_vault.domain.workspace_config.repository import RegistrationFormRepository


@dataclass(frozen=True, kw_only=True)
class CreateRegistrationFormCommand(Command):
    workspace_id: uuid.UUID
    name: str
    applies_to: FieldTarget
    is_default: bool = False
    field_overrides: list[dict] = field(default_factory=list)


class CreateRegistrationForm:
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
        self, input: CreateRegistrationFormCommand, auth: AuthContext | None = None
    ) -> Result[RegistrationForm, DomainError]:
        require_editor(auth)

        async with self._uow:
            # Check for duplicate name+applies_to in this workspace
            existing = await self._repo.find_by_workspace(
                input.workspace_id, applies_to=input.applies_to
            )
            for form in existing:
                if form.name.lower() == input.name.strip().lower():
                    return Failure(
                        ConflictError(
                            f"Registration form '{input.name.strip()}' already exists "
                            f"for target '{input.applies_to.value}' in this workspace"
                        )
                    )

            # If setting as default, unset the existing default for this applies_to
            if input.is_default:
                for form in existing:
                    if form.is_default:
                        form.set_default(False)
                        await self._repo.save(form)

            overrides = [FieldOverride(**item) for item in input.field_overrides]
            new_form = RegistrationForm.create(
                workspace_id=input.workspace_id,
                name=input.name,
                applies_to=input.applies_to,
                is_default=input.is_default,
                field_overrides=overrides,
            )
            await self._repo.save(new_form)
            events = await self._uow.commit()
            await self._dispatcher.dispatch_all(events)
            return Success(new_form)
