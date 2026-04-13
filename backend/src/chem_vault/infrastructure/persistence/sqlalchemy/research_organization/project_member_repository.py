"""SQLAlchemy repository for project membership."""

from __future__ import annotations

import uuid

from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from chem_vault.domain.research_organization.project_membership import (
    ProjectMember,
    ProjectRole,
)
from chem_vault.infrastructure.persistence.sqlalchemy.research_organization.models import (
    ProjectMemberModel,
    ProjectModel,
)
from chem_vault.infrastructure.persistence.unit_of_work import AsyncUnitOfWork


class SQLAlchemyProjectMemberRepository:
    """Manages project_members table — not an aggregate repo (no versioning)."""

    def __init__(self, uow: AsyncUnitOfWork) -> None:
        self._uow = uow

    async def find_accessible_project_ids(
        self, workspace_id: uuid.UUID, user_id: uuid.UUID
    ) -> list[uuid.UUID]:
        """Return project IDs for which user has any role, scoped to workspace."""
        stmt = (
            select(ProjectMemberModel.project_id)
            .join(ProjectModel, ProjectMemberModel.project_id == ProjectModel.id)
            .where(
                ProjectModel.workspace_id == workspace_id,
                ProjectMemberModel.user_id == user_id,
            )
        )
        result = await self._uow.session.execute(stmt)
        return list(result.scalars().all())

    async def find_members(
        self, workspace_id: uuid.UUID, project_id: uuid.UUID
    ) -> list[ProjectMember]:
        """Return all members of a project, scoped to workspace (defense-in-depth)."""
        ws_project_subq = select(ProjectModel.id).where(
            ProjectModel.id == project_id,
            ProjectModel.workspace_id == workspace_id,
        )
        stmt = select(ProjectMemberModel).where(
            ProjectMemberModel.project_id == project_id,
            ProjectMemberModel.project_id.in_(ws_project_subq),
        )
        result = await self._uow.session.execute(stmt)
        return [
            ProjectMember(
                project_id=m.project_id,
                user_id=m.user_id,
                role=ProjectRole(m.role),
            )
            for m in result.scalars().all()
        ]

    async def add_member(
        self, workspace_id: uuid.UUID, project_id: uuid.UUID, user_id: uuid.UUID, role: ProjectRole
    ) -> None:
        """Add a member to a project, scoped to workspace (defense-in-depth)."""
        # Verify project belongs to workspace before inserting
        ownership_stmt = select(ProjectModel.id).where(
            ProjectModel.id == project_id,
            ProjectModel.workspace_id == workspace_id,
        )
        ownership_result = await self._uow.session.execute(ownership_stmt)
        if ownership_result.scalar_one_or_none() is None:
            return
        stmt = (
            pg_insert(ProjectMemberModel)
            .values(project_id=project_id, user_id=user_id, role=role.value)
            .on_conflict_do_nothing()
        )
        await self._uow.session.execute(stmt)

    async def remove_member(
        self, workspace_id: uuid.UUID, project_id: uuid.UUID, user_id: uuid.UUID
    ) -> None:
        """Remove a member from a project, scoped to workspace (defense-in-depth)."""
        ws_project_subq = select(ProjectModel.id).where(
            ProjectModel.id == project_id,
            ProjectModel.workspace_id == workspace_id,
        )
        stmt = delete(ProjectMemberModel).where(
            ProjectMemberModel.project_id == project_id,
            ProjectMemberModel.user_id == user_id,
            ProjectMemberModel.project_id.in_(ws_project_subq),
        )
        await self._uow.session.execute(stmt)

    async def update_role(
        self, workspace_id: uuid.UUID, project_id: uuid.UUID, user_id: uuid.UUID, role: ProjectRole
    ) -> None:
        """Update a member's role, scoped to workspace (defense-in-depth)."""
        ws_project_subq = select(ProjectModel.id).where(
            ProjectModel.id == project_id,
            ProjectModel.workspace_id == workspace_id,
        )
        stmt = (
            update(ProjectMemberModel)
            .where(
                ProjectMemberModel.project_id == project_id,
                ProjectMemberModel.user_id == user_id,
                ProjectMemberModel.project_id.in_(ws_project_subq),
            )
            .values(role=role.value)
        )
        await self._uow.session.execute(stmt)

    async def get_role(
        self, workspace_id: uuid.UUID, project_id: uuid.UUID, user_id: uuid.UUID
    ) -> ProjectRole | None:
        """Get a member's role, scoped to workspace (defense-in-depth)."""
        ws_project_subq = select(ProjectModel.id).where(
            ProjectModel.id == project_id,
            ProjectModel.workspace_id == workspace_id,
        )
        stmt = select(ProjectMemberModel.role).where(
            ProjectMemberModel.project_id == project_id,
            ProjectMemberModel.user_id == user_id,
            ProjectMemberModel.project_id.in_(ws_project_subq),
        )
        result = await self._uow.session.execute(stmt)
        row = result.scalar_one_or_none()
        return ProjectRole(row) if row is not None else None
