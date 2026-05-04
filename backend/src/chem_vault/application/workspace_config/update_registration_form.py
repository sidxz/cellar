"""UpdateRegistrationForm command — update name, field_overrides, or is_default."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from returns.result import Failure, Result, Success

from chem_vault.application.auth import AuthContext, require_editor
from chem_vault.application.shared.command import Command
from chem_vault.application.shared.event_dispatcher import EventDispatcherProtocol
from chem_vault.application.shared.sentinel import UNSET
from chem_vault.application.shared.unit_of_work import UnitOfWork
from chem_vault.domain.shared.errors import DomainError, NotFoundError
from chem_vault.domain.workspace_config.registration_form import RegistrationForm
from chem_vault.domain.workspace_config.value_objects import FieldOverride
from chem_vault.domain.workspace_config.repository import RegistrationFormRepository


@dataclass(frozen=True, kw_only=True)
class UpdateRegistrationFormCommand(Command):
    workspace_id: uuid.UUID
    form_id: uuid.UUID
    name: str | object = UNSET
    is_default: bool | object = UNSET
    field_overrides: list[dict[str, Any]] | object = UNSET


class UpdateRegistrationForm:
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
        self, input: UpdateRegistrationFormCommand, auth: AuthContext | None = None
    ) -> Result[RegistrationForm, DomainError]:
        require_editor(auth)

        async with self._uow:
            form = await self._repo.find_by_id_in_workspace(input.workspace_id, input.form_id)
            if form is None:
                return Failure(NotFoundError("RegistrationForm", str(input.form_id)))

            # If setting as default, unset the previous default for this applies_to
            if input.is_default is not UNSET and input.is_default:
                existing = await self._repo.find_by_workspace(
                    input.workspace_id, applies_to=form.applies_to
                )
                for other in existing:
                    if other.id != form.id and other.is_default:
                        other.set_default(False)
                        await self._repo.save(other)

            # Build kwargs for update() from non-UNSET fields
            update_kwargs: dict[str, Any] = {}
            if input.name is not UNSET:
                update_kwargs["name"] = input.name
            if input.field_overrides is not UNSET:
                overrides = [FieldOverride(**item) for item in input.field_overrides]  # type: ignore[union-attr]
                update_kwargs["field_overrides"] = overrides

            if update_kwargs:
                form.update(**update_kwargs)

            # Handle is_default separately via set_default
            if input.is_default is not UNSET:
                form.set_default(bool(input.is_default))

            await self._repo.save(form)
            events = await self._uow.commit()

        await self._dispatcher.dispatch_all(events)
        return Success(form)
