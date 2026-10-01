"""Putting compounds into projects — the one access rule and the one write
shared by the bulk add endpoint and single / bulk registration."""

from __future__ import annotations

import uuid

from cellar.application.auth import AuthContext, require_project_role
from cellar.domain.chemical_registration.repository import MoleculeRepository
from cellar.domain.research_organization.enums import ProjectStatus
from cellar.domain.research_organization.events import EntityAddedToProject
from cellar.domain.research_organization.project_membership import ProjectRole
from cellar.domain.research_organization.repository import (
    ProjectMemberRepository,
    ProjectRepository,
)
from cellar.domain.shared.errors import (
    AuthorizationError,
    DomainError,
    NotFoundError,
    ValidationError,
)


class ProjectAccess:
    """May this caller add compounds to these projects?

    Every project must exist in the workspace and be active, and the caller must
    be a workspace admin or hold at least the editor project role. System calls
    (``auth=None``) skip the role check. Run inside an open unit of work — the
    repositories share it.
    """

    def __init__(
        self, project_repo: ProjectRepository, member_repo: ProjectMemberRepository
    ) -> None:
        self._project_repo = project_repo
        self._member_repo = member_repo

    async def check_editable(
        self,
        workspace_id: uuid.UUID,
        project_ids: list[uuid.UUID],
        auth: AuthContext | None,
    ) -> DomainError | None:
        """The first reason the caller may not link to ``project_ids``, else None."""
        for project_id in dict.fromkeys(project_ids):
            project = await self._project_repo.find_by_id_in_workspace(workspace_id, project_id)
            if project is None:
                return NotFoundError("Project", str(project_id))
            if project.status == ProjectStatus.ARCHIVED:
                return ValidationError(f"Project '{project.name}' is archived")
            if auth is None:
                continue
            role = await self._member_repo.get_role(workspace_id, project_id, auth.user_id)
            try:
                require_project_role(auth, role, ProjectRole.EDITOR)
            except AuthorizationError as exc:
                return AuthorizationError(f"{exc.message} ('{project.name}')", detail=exc.detail)
        return None


async def link_molecules_to_projects(
    molecule_repo: MoleculeRepository,
    workspace_id: uuid.UUID,
    project_ids: list[uuid.UUID],
    molecule_ids: list[uuid.UUID],
) -> list[EntityAddedToProject]:
    """Link every molecule to every project; one audit event per *new* link.

    The caller commits its unit of work, then dispatches the returned events.
    """
    events: list[EntityAddedToProject] = []
    for project_id in dict.fromkeys(project_ids):
        added = await molecule_repo.add_to_project_many(workspace_id, project_id, molecule_ids)
        events.extend(
            EntityAddedToProject(
                aggregate_id=project_id,
                aggregate_type="Project",
                workspace_id=workspace_id,
                entity_type="molecule",
                entity_id=molecule_id,
                project_id=project_id,
            )
            for molecule_id in added
        )
    return events
