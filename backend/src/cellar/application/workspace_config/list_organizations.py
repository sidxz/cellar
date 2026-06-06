"""ListOrganizations query — retrieve all organizations for a workspace."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Result, Success

from cellar.application.auth import AuthContext, require_same_workspace, require_workspace_role
from cellar.application.shared.pagination import PageResult
from cellar.application.shared.query import Query
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.shared.errors import DomainError
from cellar.domain.workspace_config.organization import Organization
from cellar.domain.workspace_config.repository import OrganizationRepository


@dataclass(frozen=True, kw_only=True)
class ListOrganizationsQuery(Query):
    workspace_id: uuid.UUID
    include_inactive: bool = False
    cursor_id: uuid.UUID | None = None
    limit: int | None = None


class ListOrganizations:
    def __init__(self, uow: UnitOfWork, repo: OrganizationRepository) -> None:
        self._uow = uow
        self._repo = repo

    async def __call__(
        self, input: ListOrganizationsQuery, auth: AuthContext | None = None
    ) -> Result[PageResult[Organization], DomainError]:
        require_workspace_role(auth, "viewer")
        require_same_workspace(auth, input.workspace_id)
        async with self._uow:
            effective_limit = input.limit
            fetch_limit = effective_limit + 1 if effective_limit is not None else None
            orgs = await self._repo.find_by_workspace(
                input.workspace_id,
                include_inactive=input.include_inactive,
                cursor_id=input.cursor_id,
                limit=fetch_limit,
            )

            next_cursor: str | None = None
            if effective_limit is not None and len(orgs) > effective_limit:
                orgs = orgs[:effective_limit]
                next_cursor = str(orgs[-1].id)

            return Success(PageResult(items=orgs, next_cursor=next_cursor))
