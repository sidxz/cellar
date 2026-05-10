"""UpdateProject command — partial update of an existing project."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from returns.result import Failure, Result, Success

from chem_vault.application.auth import AuthContext, require_editor
from chem_vault.application.shared.command import Command
from chem_vault.application.shared.event_dispatcher import EventDispatcherProtocol
from chem_vault.application.shared.unit_of_work import UnitOfWork
from chem_vault.application.shared.sentinel import UNSET
from chem_vault.domain.research_organization.project import Project
from chem_vault.domain.research_organization.repository import ProjectRepository
from chem_vault.domain.shared.errors import ConflictError, DomainError, NotFoundError


@dataclass(frozen=True, kw_only=True)
class UpdateProjectCommand(Command):
    workspace_id: uuid.UUID
    project_id: uuid.UUID
    name: str | object = UNSET
    description: str | None | object = UNSET


class UpdateProject:
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
        self, input: UpdateProjectCommand, auth: AuthContext | None = None
    ) -> Result[Project, DomainError]:
        require_editor(auth)

        async with self._uow:
            project = await self._repo.find_by_id_in_workspace(input.workspace_id, input.project_id)
            if project is None:
                return Failure(NotFoundError("Project", str(input.project_id)))

            # Name uniqueness check (only when caller actually provided a name)
            if input.name is not UNSET and input.name is not None:
                existing = await self._repo.find_by_name(
                    input.workspace_id, input.name.strip()
                )
                if existing is not None and existing.id != project.id:
                    return Failure(
                        ConflictError(f"Project '{input.name.strip()}' already exists")
                    )

            # Build kwargs — only include fields that were provided.
            # UNSET = field omitted; an explicit null on a required field
            # propagates to domain validation and surfaces as 422.
            fields: dict[str, Any] = {}
            if input.name is not UNSET:
                fields["name"] = input.name
            if input.description is not UNSET:
                fields["description"] = input.description

            if fields:
                project.update(**fields)
            await self._repo.save(project)
            events = await self._uow.commit()

        await self._dispatcher.dispatch_all(events)
        return Success(project)
