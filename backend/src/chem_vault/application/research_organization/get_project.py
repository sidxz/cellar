"""GetProject / ListProjects queries — retrieve project(s) by ID or workspace."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Failure, Result, Success

from chem_vault.application.shared.query import Query
from chem_vault.application.shared.unit_of_work import UnitOfWork
from chem_vault.domain.research_organization.project import Project
from chem_vault.domain.research_organization.repository import ProjectRepository
from chem_vault.domain.shared.errors import DomainError, NotFoundError


@dataclass(frozen=True, kw_only=True)
class GetProjectQuery(Query):
    workspace_id: uuid.UUID
    project_id: uuid.UUID


class GetProject:
    def __init__(self, uow: UnitOfWork, repo: ProjectRepository) -> None:
        self._uow = uow
        self._repo = repo

    async def __call__(
        self, input: GetProjectQuery
    ) -> Result[Project, DomainError]:
        async with self._uow:
            project = await self._repo.find_by_id(input.project_id)
            if project is None or project.workspace_id != input.workspace_id:
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
        self, input: ListProjectsQuery
    ) -> Result[list[Project], DomainError]:
        async with self._uow:
            projects = await self._repo.find_by_workspace(input.workspace_id)
            return Success(projects)
