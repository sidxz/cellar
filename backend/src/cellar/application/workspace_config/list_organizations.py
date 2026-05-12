"""ListOrganizations query — retrieve all organizations for a workspace."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Result, Success

from cellar.application.auth import AuthContext, require_workspace_role
from cellar.application.shared.query import Query
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.shared.errors import DomainError
from cellar.domain.workspace_config.organization import Organization
from cellar.domain.workspace_config.repository import OrganizationRepository


@dataclass(frozen=True, kw_only=True)
class ListOrganizationsQuery(Query):
    workspace_id: uuid.UUID
    include_inactive: bool = False


class ListOrganizations:
    def __init__(self, uow: UnitOfWork, repo: OrganizationRepository) -> None:
        self._uow = uow
        self._repo = repo

    async def __call__(
        self, input: ListOrganizationsQuery, auth: AuthContext | None = None
    ) -> Result[list[Organization], DomainError]:
        require_workspace_role(auth, "viewer")
        async with self._uow:
            orgs = await self._repo.find_by_workspace(
                input.workspace_id, include_inactive=input.include_inactive
            )
            return Success(orgs)
