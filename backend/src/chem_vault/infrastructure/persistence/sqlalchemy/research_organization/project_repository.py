"""SQLAlchemy repository for Project aggregates."""

from __future__ import annotations

import uuid

from sqlalchemy import select

from chem_vault.domain.research_organization.project import Project, ProjectStatus
from chem_vault.infrastructure.persistence.sqlalchemy.base_repository import (
    SQLAlchemyRepository,
)
from chem_vault.infrastructure.persistence.sqlalchemy.research_organization.models import (
    ProjectModel,
)


class SQLAlchemyProjectRepository(
    SQLAlchemyRepository[Project, ProjectModel]
):
    model_class = ProjectModel

    def _to_domain(self, model: ProjectModel) -> Project:
        return Project(
            id=model.id,
            workspace_id=model.workspace_id,
            name=model.name,
            description=model.description,
            status=ProjectStatus(model.status),
            created_by=model.created_by,
            archived_by=model.archived_by,
            archived_at=model.archived_at,
            created_at=model.created_at,
            updated_at=model.updated_at,
            version=model.version,
        )

    def _to_model(self, aggregate: Project) -> ProjectModel:
        return ProjectModel(
            id=aggregate.id,
            workspace_id=aggregate.workspace_id,
            name=aggregate.name,
            description=aggregate.description,
            status=aggregate.status.value,
            created_by=aggregate.created_by,
            archived_by=aggregate.archived_by,
            archived_at=aggregate.archived_at,
            version=aggregate.version,
        )

    def _update_model(self, model: ProjectModel, aggregate: Project) -> None:
        model.name = aggregate.name
        model.description = aggregate.description
        model.status = aggregate.status.value
        model.archived_by = aggregate.archived_by
        model.archived_at = aggregate.archived_at

    async def find_by_workspace(
        self, workspace_id: uuid.UUID
    ) -> list[Project]:
        stmt = (
            select(ProjectModel)
            .where(ProjectModel.workspace_id == workspace_id)
            .order_by(ProjectModel.name)
        )
        result = await self._session.execute(stmt)
        return [self._to_domain_tracked(m) for m in result.scalars()]

    async def find_by_name(
        self, workspace_id: uuid.UUID, name: str
    ) -> Project | None:
        stmt = select(ProjectModel).where(
            ProjectModel.workspace_id == workspace_id,
            ProjectModel.name == name,
        )
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        return self._to_domain_tracked(model) if model else None
