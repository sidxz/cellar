"""CreateCustomField command — create a new custom field definition."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from returns.result import Failure, Result, Success

from cellar.application.auth import AuthContext, require_editor, require_same_workspace
from cellar.application.shared.command import Command
from cellar.application.shared.event_dispatcher import EventDispatcherProtocol
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.shared.errors import ConflictError, DomainError
from cellar.domain.workspace_config.custom_field_definition import CustomFieldDefinition
from cellar.domain.workspace_config.enums import FieldDataType, FieldTarget
from cellar.domain.workspace_config.repository import CustomFieldDefinitionRepository


@dataclass(frozen=True, kw_only=True)
class CreateCustomFieldCommand(Command):
    workspace_id: uuid.UUID
    name: str
    label: str
    data_type: str
    applies_to: str
    is_required: bool = False
    default_value: Any | None = None
    display_order: int = 0
    pick_list_values: list[str] | None = None
    vocabulary_id: uuid.UUID | None = None


class CreateCustomField:
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
        self, input: CreateCustomFieldCommand, auth: AuthContext | None = None
    ) -> Result[CustomFieldDefinition, DomainError]:
        require_editor(auth)
        require_same_workspace(auth, input.workspace_id)

        async with self._uow:
            # Check for duplicate name+applies_to in this workspace
            existing = await self._repo.find_by_workspace(
                input.workspace_id,
                applies_to=FieldTarget(input.applies_to),
                active_only=False,
            )
            for cfd in existing:
                if cfd.name == input.name.strip():
                    return Failure(
                        ConflictError(
                            f"Custom field '{input.name.strip()}' already exists "
                            f"for target '{input.applies_to}'"
                        )
                    )

            cfd = CustomFieldDefinition.create(
                workspace_id=input.workspace_id,
                name=input.name,
                label=input.label,
                data_type=FieldDataType(input.data_type),
                applies_to=FieldTarget(input.applies_to),
                is_required=input.is_required,
                default_value=input.default_value,
                display_order=input.display_order,
                pick_list_values=input.pick_list_values,
                vocabulary_id=input.vocabulary_id,
            )
            await self._repo.save(cfd)
            events = await self._uow.commit()

        await self._dispatcher.dispatch_all(events)
        return Success(cfd)
