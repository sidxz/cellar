"""Use cases for managing molecule-project associations."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Failure, Result, Success

from chem_vault.application.auth import AuthContext, require_editor, require_project_role
from chem_vault.application.shared.command import Command
from chem_vault.application.shared.event_dispatcher import EventDispatcherProtocol
from chem_vault.application.shared.query import Query
from chem_vault.application.shared.unit_of_work import UnitOfWork
from chem_vault.domain.chemical_registration.repository import MoleculeRepository
from chem_vault.domain.research_organization.events import (
    EntityAddedToProject,
    EntityRemovedFromProject,
)
from chem_vault.domain.research_organization.project_membership import ProjectRole
from chem_vault.domain.research_organization.repository import (
    ProjectMemberRepository,
    ProjectRepository,
)
from chem_vault.domain.shared.errors import DomainError, NotFoundError


# ---------------------------------------------------------------------------
# AddMoleculeToProject
# ---------------------------------------------------------------------------


@dataclass(frozen=True, kw_only=True)
class AddMoleculeToProjectCommand(Command):
    workspace_id: uuid.UUID
    project_id: uuid.UUID
    molecule_id: uuid.UUID


class AddMoleculeToProject:
    """Associate a molecule with a project."""

    def __init__(
        self,
        uow: UnitOfWork,
        project_repo: ProjectRepository,
        molecule_repo: MoleculeRepository,
        member_repo: ProjectMemberRepository,
        dispatcher: EventDispatcherProtocol,
    ) -> None:
        self._uow = uow
        self._project_repo = project_repo
        self._molecule_repo = molecule_repo
        self._member_repo = member_repo
        self._dispatcher = dispatcher

    async def __call__(
        self, input: AddMoleculeToProjectCommand, auth: AuthContext | None = None
    ) -> Result[None, DomainError]:
        require_editor(auth)
        async with self._uow:
            project = await self._project_repo.find_by_id_in_workspace(input.workspace_id, input.project_id)
            if project is None:
                return Failure(NotFoundError("Project", str(input.project_id)))

            molecule = await self._molecule_repo.find_by_id_in_workspace(input.workspace_id, input.molecule_id)
            if molecule is None:
                return Failure(NotFoundError("Molecule", str(input.molecule_id)))

            # Check caller has at least editor-level project access (or is admin)
            if auth is not None:
                caller_role = await self._member_repo.get_role(
                    input.workspace_id, input.project_id, auth.user_id
                )
                require_project_role(auth, caller_role, ProjectRole.EDITOR)

            await self._molecule_repo.add_to_project(input.workspace_id, input.molecule_id, input.project_id)

            events = await self._uow.commit()

        events.append(EntityAddedToProject(
            aggregate_id=input.project_id,
            aggregate_type="Project",
            workspace_id=input.workspace_id,
            entity_type="molecule",
            entity_id=input.molecule_id,
            project_id=input.project_id,
        ))
        await self._dispatcher.dispatch_all(events)

        return Success(None)


# ---------------------------------------------------------------------------
# RemoveMoleculeFromProject
# ---------------------------------------------------------------------------


@dataclass(frozen=True, kw_only=True)
class RemoveMoleculeFromProjectCommand(Command):
    workspace_id: uuid.UUID
    project_id: uuid.UUID
    molecule_id: uuid.UUID


class RemoveMoleculeFromProject:
    """Remove a molecule's association with a project."""

    def __init__(
        self,
        uow: UnitOfWork,
        project_repo: ProjectRepository,
        molecule_repo: MoleculeRepository,
        member_repo: ProjectMemberRepository,
        dispatcher: EventDispatcherProtocol,
    ) -> None:
        self._uow = uow
        self._project_repo = project_repo
        self._molecule_repo = molecule_repo
        self._member_repo = member_repo
        self._dispatcher = dispatcher

    async def __call__(
        self, input: RemoveMoleculeFromProjectCommand, auth: AuthContext | None = None
    ) -> Result[None, DomainError]:
        require_editor(auth)
        async with self._uow:
            project = await self._project_repo.find_by_id_in_workspace(input.workspace_id, input.project_id)
            if project is None:
                return Failure(NotFoundError("Project", str(input.project_id)))

            molecule = await self._molecule_repo.find_by_id_in_workspace(input.workspace_id, input.molecule_id)
            if molecule is None:
                return Failure(NotFoundError("Molecule", str(input.molecule_id)))

            # Check caller has at least editor-level project access (or is admin)
            if auth is not None:
                caller_role = await self._member_repo.get_role(
                    input.workspace_id, input.project_id, auth.user_id
                )
                require_project_role(auth, caller_role, ProjectRole.EDITOR)

            await self._molecule_repo.remove_from_project(
                input.workspace_id, input.molecule_id, input.project_id
            )

            events = await self._uow.commit()

        events.append(EntityRemovedFromProject(
            aggregate_id=input.project_id,
            aggregate_type="Project",
            workspace_id=input.workspace_id,
            entity_type="molecule",
            entity_id=input.molecule_id,
            project_id=input.project_id,
        ))
        await self._dispatcher.dispatch_all(events)

        return Success(None)


# ---------------------------------------------------------------------------
# ListMoleculeProjects
# ---------------------------------------------------------------------------


@dataclass(frozen=True, kw_only=True)
class ListMoleculeProjectsQuery(Query):
    workspace_id: uuid.UUID
    molecule_id: uuid.UUID


class ListMoleculeProjects:
    """Return all project IDs that a molecule belongs to."""

    def __init__(
        self,
        uow: UnitOfWork,
        molecule_repo: MoleculeRepository,
    ) -> None:
        self._uow = uow
        self._molecule_repo = molecule_repo

    async def __call__(
        self, input: ListMoleculeProjectsQuery, auth: AuthContext | None = None
    ) -> Result[list[uuid.UUID], DomainError]:
        async with self._uow:
            molecule = await self._molecule_repo.find_by_id_in_workspace(input.workspace_id, input.molecule_id)
            if molecule is None:
                return Failure(NotFoundError("Molecule", str(input.molecule_id)))

            project_ids = await self._molecule_repo.find_project_ids(input.workspace_id, input.molecule_id)
            return Success(project_ids)
