"""ListCustomFields query — list custom field definitions for a workspace."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Result, Success

from chem_vault.application.shared.query import Query
from chem_vault.domain.shared.errors import DomainError
from chem_vault.domain.workspace_config.custom_field_definition import CustomFieldDefinition
from chem_vault.domain.workspace_config.enums import FieldTarget
from chem_vault.domain.workspace_config.repository import CustomFieldDefinitionRepository


@dataclass(frozen=True, kw_only=True)
class ListCustomFieldsQuery(Query):
    workspace_id: uuid.UUID
    applies_to: str | None = None
    active_only: bool = True


class ListCustomFields:
    def __init__(self, repo: CustomFieldDefinitionRepository) -> None:
        self._repo = repo

    async def __call__(
        self, input: ListCustomFieldsQuery
    ) -> Result[list[CustomFieldDefinition], DomainError]:
        target = FieldTarget(input.applies_to) if input.applies_to else None
        results = await self._repo.find_by_workspace(
            input.workspace_id,
            applies_to=target,
            active_only=input.active_only,
        )
        return Success(results)
