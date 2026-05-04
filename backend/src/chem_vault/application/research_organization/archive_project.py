"""ArchiveProject command — mark a project as archived."""

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
from chem_vault.domain.shared.errors import DomainError, NotFoundError


@dataclass(frozen=True, kw_only=True)
class ArchiveProjectCommand(Command):
    workspace_id: uuid.UUID
    project_id: uuid.UUID
    archived_by: uuid.UUID


class ArchiveProject:
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
        self, input: ArchiveProjectCommand, auth: AuthContext | None = None
    ) -> Result[Project, DomainError]:
        require_editor(auth)

        async with self._uow:
            project = await self._repo.find_by_id_in_workspace(input.workspace_id, input.project_id)
            if project is None:
                return Failure(NotFoundError("Project", str(input.project_id)))

            project.archive(archived_by=input.archived_by)
            await self._repo.save(project)
            events = await self._uow.commit()

        await self._dispatcher.dispatch_all(events)
        return Success(project)
