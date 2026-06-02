"""GetProject / ListProjects queries — retrieve project(s) by ID or workspace."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Failure, Result, Success

from cellar.application.auth import AuthContext, require_workspace_role
from cellar.application.shared.pagination import PageResult
from cellar.application.shared.query import Query
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.research_organization.project import Project
from cellar.domain.research_organization.repository import ProjectRepository
from cellar.domain.shared.errors import DomainError, NotFoundError


@dataclass(frozen=True, kw_only=True)
class GetProjectQuery(Query):
    workspace_id: uuid.UUID
    project_id: uuid.UUID


class GetProject:
    def __init__(self, uow: UnitOfWork, repo: ProjectRepository) -> None:
        self._uow = uow
        self._repo = repo

    async def __call__(
        self, input: GetProjectQuery, auth: AuthContext | None = None
    ) -> Result[Project, DomainError]:
        require_workspace_role(auth, "viewer")
        async with self._uow:
            project = await self._repo.find_by_id_in_workspace(
                input.workspace_id, input.project_id
            )
            if project is None:
                return Failure(NotFoundError("Project", str(input.project_id)))
            return Success(project)


@dataclass(frozen=True, kw_only=True)
class ListProjectsQuery(Query):
    workspace_id: uuid.UUID
    cursor_id: uuid.UUID | None = None
    limit: int | None = None
    tags: list[uuid.UUID] | None = None
    tag_logic: str = "any"


class ListProjects:
    def __init__(self, uow: UnitOfWork, repo: ProjectRepository) -> None:
        self._uow = uow
        self._repo = repo

    async def __call__(
        self, input: ListProjectsQuery, auth: AuthContext | None = None
    ) -> Result[PageResult[Project], DomainError]:
        require_workspace_role(auth, "viewer")
        async with self._uow:
            effective_limit = input.limit
            fetch_limit = effective_limit + 1 if effective_limit is not None else None
            projects = await self._repo.find_by_workspace(
                input.workspace_id,
                cursor_id=input.cursor_id,
                limit=fetch_limit,
                tags=input.tags,
                tag_logic=input.tag_logic,
            )

            next_cursor: str | None = None
            if effective_limit is not None and len(projects) > effective_limit:
                projects = projects[:effective_limit]
                next_cursor = str(projects[-1].id)

            return Success(PageResult(items=projects, next_cursor=next_cursor))
