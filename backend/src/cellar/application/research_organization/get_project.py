"""GetProject / ListProjects queries — retrieve project(s) by ID or workspace."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Failure, Result, Success

from cellar.application.auth import AuthContext, require_workspace_role
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


class ListProjects:
    def __init__(self, uow: UnitOfWork, repo: ProjectRepository) -> None:
        self._uow = uow
        self._repo = repo

    async def __call__(
        self, input: ListProjectsQuery, auth: AuthContext | None = None
    ) -> Result[list[Project], DomainError]:
        require_workspace_role(auth, "viewer")
        async with self._uow:
            projects = await self._repo.find_by_workspace(input.workspace_id)
            return Success(projects)
