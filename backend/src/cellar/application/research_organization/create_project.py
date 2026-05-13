"""CreateProject command — register a new research project in a workspace."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Failure, Result, Success

from cellar.application.auth import AuthContext, require_editor
from cellar.application.shared.command import Command
from cellar.application.shared.event_dispatcher import EventDispatcherProtocol
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.research_organization.project import Project
from cellar.domain.research_organization.project_membership import ProjectRole
from cellar.domain.research_organization.repository import (
    ProjectMemberRepository,
    ProjectRepository,
)
from cellar.domain.shared.errors import ConflictError, DomainError


@dataclass(frozen=True, kw_only=True)
class CreateProjectCommand(Command):
    workspace_id: uuid.UUID
    name: str
    description: str | None = None
    created_by: uuid.UUID


class CreateProject:
    def __init__(
        self,
        uow: UnitOfWork,
        repo: ProjectRepository,
        dispatcher: EventDispatcherProtocol,
        member_repo: ProjectMemberRepository | None = None,
    ) -> None:
        self._uow = uow
        self._repo = repo
        self._dispatcher = dispatcher
        self._member_repo = member_repo

    async def __call__(
        self, input: CreateProjectCommand, auth: AuthContext | None = None
    ) -> Result[Project, DomainError]:
        require_editor(auth)

        async with self._uow:
            existing = await self._repo.find_by_name(input.workspace_id, input.name.strip())
            if existing is not None:
                return Failure(ConflictError(f"Project '{input.name.strip()}' already exists"))

            project = Project.create(
                workspace_id=input.workspace_id,
                name=input.name,
                description=input.description,
                created_by=input.created_by,
            )
            await self._repo.save(project)

            # Auto-add creator as project manager
            if self._member_repo is not None:
                await self._member_repo.add_member(
                    input.workspace_id, project.id, input.created_by, ProjectRole.MANAGER
                )

            events = await self._uow.commit()

        await self._dispatcher.dispatch_all(events)
        return Success(project)
