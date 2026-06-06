"""ListCustomFields query — list custom field definitions for a workspace."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Result, Success

from cellar.application.auth import AuthContext, require_same_workspace, require_workspace_role
from cellar.application.shared.query import Query
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.shared.errors import DomainError
from cellar.domain.workspace_config.custom_field_definition import CustomFieldDefinition
from cellar.domain.workspace_config.enums import FieldTarget
from cellar.domain.workspace_config.repository import CustomFieldDefinitionRepository


@dataclass(frozen=True, kw_only=True)
class ListCustomFieldsQuery(Query):
    workspace_id: uuid.UUID
    applies_to: str | None = None
    active_only: bool = True


class ListCustomFields:
    def __init__(self, uow: UnitOfWork, repo: CustomFieldDefinitionRepository) -> None:
        self._uow = uow
        self._repo = repo

    async def __call__(
        self, input: ListCustomFieldsQuery, auth: AuthContext | None = None
    ) -> Result[list[CustomFieldDefinition], DomainError]:
        require_workspace_role(auth, "viewer")
        require_same_workspace(auth, input.workspace_id)
        async with self._uow:
            target = FieldTarget(input.applies_to) if input.applies_to else None
            results = await self._repo.find_by_workspace(
                input.workspace_id,
                applies_to=target,
                active_only=input.active_only,
            )
            return Success(results)
