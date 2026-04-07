"""ListRegistrationForms query — list registration form templates for a workspace."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Result, Success

from chem_vault.application.shared.query import Query
from chem_vault.domain.shared.errors import DomainError
from chem_vault.domain.workspace_config.enums import FieldTarget
from chem_vault.domain.workspace_config.registration_form import RegistrationForm
from chem_vault.domain.workspace_config.repository import RegistrationFormRepository


@dataclass(frozen=True, kw_only=True)
class ListRegistrationFormsQuery(Query):
    workspace_id: uuid.UUID
    applies_to: FieldTarget | None = None


class ListRegistrationForms:
    def __init__(self, repo: RegistrationFormRepository) -> None:
        self._repo = repo

    async def __call__(
        self, input: ListRegistrationFormsQuery
    ) -> Result[list[RegistrationForm], DomainError]:
        results = await self._repo.find_by_workspace(
            input.workspace_id,
            applies_to=input.applies_to,
        )
        return Success(results)
