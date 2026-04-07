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
        self._session = uow.session

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
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def find_members(self, project_id: uuid.UUID) -> list[ProjectMember]:
        stmt = select(ProjectMemberModel).where(
            ProjectMemberModel.project_id == project_id
        )
        result = await self._session.execute(stmt)
        return [
            ProjectMember(
                project_id=m.project_id,
                user_id=m.user_id,
                role=ProjectRole(m.role),
            )
            for m in result.scalars().all()
        ]

    async def add_member(
        self, project_id: uuid.UUID, user_id: uuid.UUID, role: ProjectRole
    ) -> None:
        stmt = (
            pg_insert(ProjectMemberModel)
            .values(project_id=project_id, user_id=user_id, role=role.value)
            .on_conflict_do_nothing()
        )
        await self._session.execute(stmt)

    async def remove_member(
        self, project_id: uuid.UUID, user_id: uuid.UUID
    ) -> None:
        stmt = delete(ProjectMemberModel).where(
            ProjectMemberModel.project_id == project_id,
            ProjectMemberModel.user_id == user_id,
        )
        await self._session.execute(stmt)

    async def update_role(
        self, project_id: uuid.UUID, user_id: uuid.UUID, role: ProjectRole
    ) -> None:
        stmt = (
            update(ProjectMemberModel)
            .where(
                ProjectMemberModel.project_id == project_id,
                ProjectMemberModel.user_id == user_id,
            )
            .values(role=role.value)
        )
        await self._session.execute(stmt)

    async def get_role(
        self, project_id: uuid.UUID, user_id: uuid.UUID
    ) -> ProjectRole | None:
        stmt = select(ProjectMemberModel.role).where(
            ProjectMemberModel.project_id == project_id,
            ProjectMemberModel.user_id == user_id,
        )
        result = await self._session.execute(stmt)
        row = result.scalar_one_or_none()
        return ProjectRole(row) if row is not None else None
