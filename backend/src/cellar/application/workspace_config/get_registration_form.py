"""GetRegistrationForm query -- retrieve a single registration form by ID."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Failure, Result, Success

from cellar.application.auth import AuthContext, require_same_workspace, require_workspace_role
from cellar.application.shared.query import Query
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.shared.errors import DomainError, NotFoundError
from cellar.domain.workspace_config.registration_form import RegistrationForm
from cellar.domain.workspace_config.repository import RegistrationFormRepository


@dataclass(frozen=True, kw_only=True)
class GetRegistrationFormQuery(Query):
    workspace_id: uuid.UUID
    form_id: uuid.UUID


class GetRegistrationForm:
    def __init__(self, uow: UnitOfWork, repo: RegistrationFormRepository) -> None:
        self._uow = uow
        self._repo = repo

    async def __call__(
        self, input: GetRegistrationFormQuery, auth: AuthContext | None = None
    ) -> Result[RegistrationForm, DomainError]:
        require_workspace_role(auth, "viewer")
        require_same_workspace(auth, input.workspace_id)
        async with self._uow:
            form = await self._repo.find_by_id_in_workspace(input.workspace_id, input.form_id)
            if form is None:
                return Failure(NotFoundError("RegistrationForm", str(input.form_id)))
            return Success(form)
