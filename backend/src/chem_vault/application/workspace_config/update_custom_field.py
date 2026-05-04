"""UpdateCustomField command — update label, constraints, or status of a custom field definition."""

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
from chem_vault.domain.workspace_config.custom_field_definition import CustomFieldDefinition
from chem_vault.domain.workspace_config.repository import CustomFieldDefinitionRepository


@dataclass(frozen=True, kw_only=True)
class UpdateCustomFieldCommand(Command):
    workspace_id: uuid.UUID
    field_id: uuid.UUID
    label: str | object = UNSET
    is_required: bool | object = UNSET
    default_value: Any | object = UNSET
    display_order: int | object = UNSET
    pick_list_values: list[str] | None | object = UNSET
    vocabulary_id: uuid.UUID | None | object = UNSET
    is_active: bool | object = UNSET


class UpdateCustomField:
    def __init__(
        self,
        uow: UnitOfWork,
        repo: CustomFieldDefinitionRepository,
        dispatcher: EventDispatcherProtocol,
    ) -> None:
        self._uow = uow
        self._repo = repo
        self._dispatcher = dispatcher

    async def __call__(
        self, input: UpdateCustomFieldCommand, auth: AuthContext | None = None
    ) -> Result[CustomFieldDefinition, DomainError]:
        require_editor(auth)

        async with self._uow:
            cfd = await self._repo.find_by_id_in_workspace(input.workspace_id, input.field_id)
            if cfd is None:
                return Failure(NotFoundError("CustomFieldDefinition", str(input.field_id)))

            # Build kwargs for update() from non-UNSET fields
            update_kwargs: dict[str, Any] = {}
            for attr in ("label", "is_required", "default_value", "display_order",
                         "pick_list_values", "vocabulary_id"):
                val = getattr(input, attr)
                if val is not UNSET:
                    update_kwargs[attr] = val

            if update_kwargs:
                cfd.update(**update_kwargs)

            # Handle is_active separately (activate/deactivate calls)
            if input.is_active is not UNSET:
                if input.is_active:
                    cfd.activate()
                else:
                    cfd.deactivate()

            await self._repo.save(cfd)
            events = await self._uow.commit()

        await self._dispatcher.dispatch_all(events)
        return Success(cfd)
