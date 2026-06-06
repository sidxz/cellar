"""ListRegistrationForms query — list registration form templates for a workspace."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Result, Success

from cellar.application.auth import AuthContext, require_same_workspace, require_workspace_role
from cellar.application.shared.query import Query
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.shared.errors import DomainError
from cellar.domain.workspace_config.enums import FieldTarget
from cellar.domain.workspace_config.registration_form import RegistrationForm
from cellar.domain.workspace_config.repository import RegistrationFormRepository


@dataclass(frozen=True, kw_only=True)
class ListRegistrationFormsQuery(Query):
    workspace_id: uuid.UUID
    applies_to: FieldTarget | None = None


class ListRegistrationForms:
    def __init__(self, uow: UnitOfWork, repo: RegistrationFormRepository) -> None:
        self._uow = uow
        self._repo = repo

    async def __call__(
        self, input: ListRegistrationFormsQuery, auth: AuthContext | None = None
    ) -> Result[list[RegistrationForm], DomainError]:
        require_workspace_role(auth, "viewer")
        require_same_workspace(auth, input.workspace_id)
        async with self._uow:
            results = await self._repo.find_by_workspace(
                input.workspace_id,
                applies_to=input.applies_to,
            )
            return Success(results)
