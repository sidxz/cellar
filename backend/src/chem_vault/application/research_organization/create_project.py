"""CreateProject command — register a new research project in a workspace."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Failure, Result, Success

from chem_vault.application.auth import AuthContext, require_editor
from chem_vault.application.shared.command import Command
from chem_vault.application.shared.event_dispatcher import EventDispatcherProtocol
from chem_vault.application.shared.unit_of_work import UnitOfWork
from chem_vault.domain.research_organization.project import Project
from chem_vault.domain.research_organization.repository import ProjectRepository
from chem_vault.domain.shared.errors import ConflictError, DomainError


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
    ) -> None:
        self._uow = uow
        self._repo = repo
        self._dispatcher = dispatcher

    async def __call__(
        self, input: CreateProjectCommand, auth: AuthContext | None = None
    ) -> Result[Project, DomainError]:
        require_editor(auth)

        async with self._uow:
            existing = await self._repo.find_by_name(input.workspace_id, input.name.strip())
            if existing is not None:
                return Failure(
                    ConflictError(f"Project '{input.name.strip()}' already exists")
                )

            project = Project.create(
                workspace_id=input.workspace_id,
                name=input.name,
                description=input.description,
                created_by=input.created_by,
            )
            await self._repo.save(project)
            events = await self._uow.commit()
            await self._dispatcher.dispatch_all(events)
            return Success(project)
