"""GetProjectScopeStats query — counts of molecules / protocols / runs per project."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Result, Success

from cellar.application.auth import AuthContext, require_same_workspace, require_workspace_role
from cellar.application.shared.query import Query
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.research_organization.project_scope_stats import ProjectScopeStats
from cellar.domain.research_organization.repository import ProjectRepository
from cellar.domain.shared.errors import DomainError


@dataclass(frozen=True, kw_only=True)
class GetProjectScopeStatsQuery(Query):
    workspace_id: uuid.UUID
    project_ids: tuple[uuid.UUID, ...]


class GetProjectScopeStats:
    def __init__(self, uow: UnitOfWork, repo: ProjectRepository) -> None:
        self._uow = uow
        self._repo = repo

    async def __call__(
        self, input: GetProjectScopeStatsQuery, auth: AuthContext | None = None
    ) -> Result[dict[uuid.UUID, ProjectScopeStats], DomainError]:
        require_workspace_role(auth, "viewer")
        require_same_workspace(auth, input.workspace_id)
        async with self._uow:
            if not input.project_ids:
                return Success({})
            stats = await self._repo.get_scope_stats(input.workspace_id, list(input.project_ids))
            return Success(stats)
