"""ListProtocolForms query — list protocol form templates for a workspace."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Result, Success

from cellar.application.auth import AuthContext, require_workspace_role
from cellar.application.shared.query import Query
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.shared.errors import DomainError
from cellar.domain.workspace_config.protocol_form import ProtocolForm
from cellar.domain.workspace_config.repository import ProtocolFormRepository


@dataclass(frozen=True, kw_only=True)
class ListProtocolFormsQuery(Query):
    workspace_id: uuid.UUID


class ListProtocolForms:
    def __init__(self, uow: UnitOfWork, repo: ProtocolFormRepository) -> None:
        self._uow = uow
        self._repo = repo

    async def __call__(
        self, input: ListProtocolFormsQuery, auth: AuthContext | None = None
    ) -> Result[list[ProtocolForm], DomainError]:
        require_workspace_role(auth, "viewer")
        async with self._uow:
            results = await self._repo.find_by_workspace(input.workspace_id)
            return Success(results)
