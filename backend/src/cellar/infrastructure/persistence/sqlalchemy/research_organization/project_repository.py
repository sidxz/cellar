"""SQLAlchemy repository for Project aggregates."""

from __future__ import annotations

import uuid

from sqlalchemy import func, select

from cellar.domain.research_organization.project import Project, ProjectStatus
from cellar.domain.research_organization.project_scope_stats import ProjectScopeStats
from cellar.infrastructure.persistence.sqlalchemy.base_repository import (
    SQLAlchemyRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.research_organization.models import (
    ProjectModel,
    molecule_projects,
)
from cellar.infrastructure.persistence.sqlalchemy.screening_assay.models import (
    RunModel,
    protocol_projects,
)


class SQLAlchemyProjectRepository(SQLAlchemyRepository[Project, ProjectModel]):
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

    async def find_by_workspace(self, workspace_id: uuid.UUID) -> list[Project]:
        stmt = (
            select(ProjectModel)
            .where(ProjectModel.workspace_id == workspace_id)
            .order_by(ProjectModel.name)
        )
        result = await self._session.execute(stmt)
        return [self._to_domain_tracked(m) for m in result.scalars()]

    async def find_by_name(self, workspace_id: uuid.UUID, name: str) -> Project | None:
        stmt = select(ProjectModel).where(
            ProjectModel.workspace_id == workspace_id,
            ProjectModel.name == name,
        )
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        return self._to_domain_tracked(model) if model else None

    async def get_scope_stats(
        self, workspace_id: uuid.UUID, project_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, ProjectScopeStats]:
        if not project_ids:
            return {}

        # Restrict to project_ids that actually live in this workspace —
        # defense-in-depth so a forged ID can't surface a count from
        # another workspace.
        scoped_ids_stmt = select(ProjectModel.id).where(
            ProjectModel.workspace_id == workspace_id,
            ProjectModel.id.in_(project_ids),
        )
        scoped_ids = {row for row in (await self._session.execute(scoped_ids_stmt)).scalars()}
        if not scoped_ids:
            return {}

        scoped_ids_list = list(scoped_ids)

        mol_stmt = (
            select(
                molecule_projects.c.project_id,
                func.count(molecule_projects.c.molecule_id),
            )
            .where(molecule_projects.c.project_id.in_(scoped_ids_list))
            .group_by(molecule_projects.c.project_id)
        )
        prot_stmt = (
            select(
                protocol_projects.c.project_id,
                func.count(protocol_projects.c.protocol_id),
            )
            .where(protocol_projects.c.project_id.in_(scoped_ids_list))
            .group_by(protocol_projects.c.project_id)
        )
        run_stmt = (
            select(
                protocol_projects.c.project_id,
                func.count(RunModel.id),
            )
            .join(RunModel, RunModel.protocol_id == protocol_projects.c.protocol_id)
            .where(protocol_projects.c.project_id.in_(scoped_ids_list))
            .group_by(protocol_projects.c.project_id)
        )

        mol_counts = dict((await self._session.execute(mol_stmt)).all())
        prot_counts = dict((await self._session.execute(prot_stmt)).all())
        run_counts = dict((await self._session.execute(run_stmt)).all())

        return {
            pid: ProjectScopeStats(
                molecule_count=mol_counts.get(pid, 0),
                protocol_count=prot_counts.get(pid, 0),
                run_count=run_counts.get(pid, 0),
            )
            for pid in scoped_ids
        }
