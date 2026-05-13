"""Use cases for managing project membership."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Failure, Result, Success

from cellar.application.auth import (
    AuthContext,
    require_editor,
    require_project_role,
    require_workspace_role,
)
from cellar.application.shared.command import Command
from cellar.application.shared.event_dispatcher import EventDispatcherProtocol
from cellar.application.shared.query import Query
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.research_organization.events import (
    ProjectMemberAdded,
    ProjectMemberRemoved,
)
from cellar.domain.research_organization.project_membership import (
    ProjectMember,
    ProjectRole,
)
from cellar.domain.research_organization.repository import (
    ProjectMemberRepository,
    ProjectRepository,
)
from cellar.domain.shared.errors import DomainError, NotFoundError, ValidationError

# ---------------------------------------------------------------------------
# AddProjectMember
# ---------------------------------------------------------------------------


@dataclass(frozen=True, kw_only=True)
class AddProjectMemberCommand(Command):
    workspace_id: uuid.UUID
    project_id: uuid.UUID
    user_id: uuid.UUID
    role: str


class AddProjectMember:
    """Add a user to a project with the given role."""

    def __init__(
        self,
        uow: UnitOfWork,
        project_repo: ProjectRepository,
        member_repo: ProjectMemberRepository,
        dispatcher: EventDispatcherProtocol,
    ) -> None:
        self._uow = uow
        self._project_repo = project_repo
        self._member_repo = member_repo
        self._dispatcher = dispatcher

    async def __call__(
        self, input: AddProjectMemberCommand, auth: AuthContext | None = None
    ) -> Result[ProjectMember, DomainError]:
        require_editor(auth)
        # Validate role string early — before any I/O
        try:
            role = ProjectRole(input.role)
        except ValueError:
            valid = [r.value for r in ProjectRole]
            return Failure(
                ValidationError(f"Invalid project role '{input.role}'. Valid roles: {valid}")
            )

        async with self._uow:
            project = await self._project_repo.find_by_id_in_workspace(
                input.workspace_id, input.project_id
            )
            if project is None:
                return Failure(NotFoundError("Project", str(input.project_id)))

            # Check caller has manager-level access (or is admin)
            if auth is not None:
                caller_role = await self._member_repo.get_role(
                    input.workspace_id, input.project_id, auth.user_id
                )
                require_project_role(auth, caller_role, ProjectRole.MANAGER)

            await self._member_repo.add_member(
                input.workspace_id, input.project_id, input.user_id, role
            )

            project.register_event(
                ProjectMemberAdded(
                    aggregate_id=input.project_id,
                    aggregate_type="Project",
                    workspace_id=input.workspace_id,
                    project_id=input.project_id,
                    user_id=input.user_id,
                    role=role.value,
                )
            )
            events = await self._uow.commit()

        await self._dispatcher.dispatch_all(events)

        member = ProjectMember(
            project_id=input.project_id,
            user_id=input.user_id,
            role=role,
        )
        return Success(member)


# ---------------------------------------------------------------------------
# RemoveProjectMember
# ---------------------------------------------------------------------------


@dataclass(frozen=True, kw_only=True)
class RemoveProjectMemberCommand(Command):
    workspace_id: uuid.UUID
    project_id: uuid.UUID
    user_id: uuid.UUID


class RemoveProjectMember:
    """Remove a user from a project."""

    def __init__(
        self,
        uow: UnitOfWork,
        project_repo: ProjectRepository,
        member_repo: ProjectMemberRepository,
        dispatcher: EventDispatcherProtocol,
    ) -> None:
        self._uow = uow
        self._project_repo = project_repo
        self._member_repo = member_repo
        self._dispatcher = dispatcher

    async def __call__(
        self, input: RemoveProjectMemberCommand, auth: AuthContext | None = None
    ) -> Result[None, DomainError]:
        require_editor(auth)
        async with self._uow:
            project = await self._project_repo.find_by_id_in_workspace(
                input.workspace_id, input.project_id
            )
            if project is None:
                return Failure(NotFoundError("Project", str(input.project_id)))

            # Check caller has manager-level access (or is admin)
            if auth is not None:
                caller_role = await self._member_repo.get_role(
                    input.workspace_id, input.project_id, auth.user_id
                )
                require_project_role(auth, caller_role, ProjectRole.MANAGER)

            await self._member_repo.remove_member(
                input.workspace_id, input.project_id, input.user_id
            )

            project.register_event(
                ProjectMemberRemoved(
                    aggregate_id=input.project_id,
                    aggregate_type="Project",
                    workspace_id=input.workspace_id,
                    project_id=input.project_id,
                    user_id=input.user_id,
                )
            )
            events = await self._uow.commit()

        await self._dispatcher.dispatch_all(events)

        return Success(None)


# ---------------------------------------------------------------------------
# UpdateProjectMemberRole
# ---------------------------------------------------------------------------


@dataclass(frozen=True, kw_only=True)
class UpdateProjectMemberRoleCommand(Command):
    workspace_id: uuid.UUID
    project_id: uuid.UUID
    user_id: uuid.UUID
    role: str


class UpdateProjectMemberRole:
    """Update the role of an existing project member."""

    def __init__(
        self,
        uow: UnitOfWork,
        project_repo: ProjectRepository,
        member_repo: ProjectMemberRepository,
        dispatcher: EventDispatcherProtocol,
    ) -> None:
        self._uow = uow
        self._project_repo = project_repo
        self._member_repo = member_repo
        self._dispatcher = dispatcher

    async def __call__(
        self, input: UpdateProjectMemberRoleCommand, auth: AuthContext | None = None
    ) -> Result[ProjectMember, DomainError]:
        require_editor(auth)
        # Validate role string early
        try:
            role = ProjectRole(input.role)
        except ValueError:
            valid = [r.value for r in ProjectRole]
            return Failure(
                ValidationError(f"Invalid project role '{input.role}'. Valid roles: {valid}")
            )

        async with self._uow:
            project = await self._project_repo.find_by_id_in_workspace(
                input.workspace_id, input.project_id
            )
            if project is None:
                return Failure(NotFoundError("Project", str(input.project_id)))

            # Check caller has manager-level access (or is admin)
            if auth is not None:
                caller_role = await self._member_repo.get_role(
                    input.workspace_id, input.project_id, auth.user_id
                )
                require_project_role(auth, caller_role, ProjectRole.MANAGER)

            # Verify target user is already a member
            existing_role = await self._member_repo.get_role(
                input.workspace_id, input.project_id, input.user_id
            )
            if existing_role is None:
                return Failure(
                    NotFoundError(f"User {input.user_id} is not a member of this project")
                )

            await self._member_repo.update_role(
                input.workspace_id, input.project_id, input.user_id, role
            )

            events = await self._uow.commit()

        await self._dispatcher.dispatch_all(events)

        member = ProjectMember(
            project_id=input.project_id,
            user_id=input.user_id,
            role=role,
        )
        return Success(member)


# ---------------------------------------------------------------------------
# ListProjectMembers
# ---------------------------------------------------------------------------


@dataclass(frozen=True, kw_only=True)
class ListProjectMembersQuery(Query):
    workspace_id: uuid.UUID
    project_id: uuid.UUID


class ListProjectMembers:
    """Return all members of a project."""

    def __init__(
        self,
        uow: UnitOfWork,
        project_repo: ProjectRepository,
        member_repo: ProjectMemberRepository,
    ) -> None:
        self._uow = uow
        self._project_repo = project_repo
        self._member_repo = member_repo

    async def __call__(
        self, input: ListProjectMembersQuery, auth: AuthContext | None = None
    ) -> Result[list[ProjectMember], DomainError]:
        require_workspace_role(auth, "viewer")
        async with self._uow:
            project = await self._project_repo.find_by_id_in_workspace(
                input.workspace_id, input.project_id
            )
            if project is None:
                return Failure(NotFoundError("Project", str(input.project_id)))

            members = await self._member_repo.find_members(input.workspace_id, input.project_id)
            return Success(members)
