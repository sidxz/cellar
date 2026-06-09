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
    CampaignModel,
    ProjectMemberModel,
    ProjectModel,
    molecule_projects,
)
from cellar.infrastructure.persistence.sqlalchemy.screening_assay.models import (
    RunModel,
    protocol_projects,
)
from cellar.infrastructure.persistence.sqlalchemy.tagging.models import (
    ProjectTagLinkModel,
)
from cellar.infrastructure.persistence.sqlalchemy.tagging.tag_filter import (
    tag_filter_subquery,
)

# Number of member ids surfaced per project for the avatar stack on the
# project card. The full membership is reported separately via member_count.
MEMBER_AVATAR_CAP = 5


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

    async def find_by_workspace(
        self,
        workspace_id: uuid.UUID,
        *,
        cursor_id: uuid.UUID | None = None,
        limit: int | None = None,
        tags: list[uuid.UUID] | None = None,
        tag_logic: str = "any",
    ) -> list[Project]:
        stmt = select(ProjectModel).where(ProjectModel.workspace_id == workspace_id)
        if tags:
            stmt = stmt.where(
                ProjectModel.id.in_(
                    tag_filter_subquery(
                        ProjectTagLinkModel, "project_id", tags, match_all=tag_logic == "all"
                    )
                )
            )
        stmt = stmt.order_by(ProjectModel.id)
        if cursor_id is not None:
            stmt = stmt.where(ProjectModel.id > cursor_id)
        if limit is not None:
            stmt = stmt.limit(limit)
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
        # another workspace. Also grab each project's own updated_at, which
        # is the baseline for last-activity (campaigns may push it later).
        scoped_stmt = select(ProjectModel.id, ProjectModel.updated_at).where(
            ProjectModel.workspace_id == workspace_id,
            ProjectModel.id.in_(project_ids),
        )
        scoped_rows = (await self._session.execute(scoped_stmt)).all()
        if not scoped_rows:
            return {}

        project_updated = {row[0]: row[1] for row in scoped_rows}
        scoped_ids_list = list(project_updated.keys())

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
        camp_stmt = (
            select(
                CampaignModel.project_id,
                func.count(CampaignModel.id),
                func.max(CampaignModel.updated_at),
            )
            .where(
                CampaignModel.workspace_id == workspace_id,
                CampaignModel.project_id.in_(scoped_ids_list),
            )
            .group_by(CampaignModel.project_id)
        )
        # Full membership count per project (drives member_count).
        member_count_stmt = (
            select(ProjectMemberModel.project_id, func.count())
            .where(ProjectMemberModel.project_id.in_(scoped_ids_list))
            .group_by(ProjectMemberModel.project_id)
        )
        # Cap the avatar-stack ids in SQL with a per-project window so a large
        # team can't starve other projects (a global LIMIT would). user_id is
        # the deterministic tiebreaker: same-transaction inserts share a
        # created_at server_default, so created_at alone is non-deterministic.
        rn = (
            func.row_number()
            .over(
                partition_by=ProjectMemberModel.project_id,
                order_by=(ProjectMemberModel.created_at, ProjectMemberModel.user_id),
            )
            .label("rn")
        )
        ranked = (
            select(ProjectMemberModel.project_id, ProjectMemberModel.user_id, rn)
            .where(ProjectMemberModel.project_id.in_(scoped_ids_list))
            .subquery()
        )
        member_ids_stmt = (
            select(ranked.c.project_id, ranked.c.user_id)
            .where(ranked.c.rn <= MEMBER_AVATAR_CAP)
            .order_by(ranked.c.project_id, ranked.c.rn)
        )

        mol_counts = dict((await self._session.execute(mol_stmt)).all())
        prot_counts = dict((await self._session.execute(prot_stmt)).all())
        run_counts = dict((await self._session.execute(run_stmt)).all())
        member_counts = dict((await self._session.execute(member_count_stmt)).all())

        camp_rows = (await self._session.execute(camp_stmt)).all()
        camp_counts = {r[0]: r[1] for r in camp_rows}
        camp_last = {r[0]: r[2] for r in camp_rows}

        members_by_project: dict[uuid.UUID, list[uuid.UUID]] = {}
        for pid, uid in (await self._session.execute(member_ids_stmt)).all():
            members_by_project.setdefault(pid, []).append(uid)

        result: dict[uuid.UUID, ProjectScopeStats] = {}
        for pid in scoped_ids_list:
            last_activity = project_updated[pid]
            last_campaign = camp_last.get(pid)
            if last_campaign is not None and (
                last_activity is None or last_campaign > last_activity
            ):
                last_activity = last_campaign
            result[pid] = ProjectScopeStats(
                molecule_count=mol_counts.get(pid, 0),
                protocol_count=prot_counts.get(pid, 0),
                run_count=run_counts.get(pid, 0),
                campaign_count=camp_counts.get(pid, 0),
                last_activity_at=last_activity,
                # member_count is the FULL count; member_ids is the SQL-capped
                # oldest MEMBER_AVATAR_CAP for the avatar stack on the card.
                member_count=member_counts.get(pid, 0),
                member_ids=tuple(members_by_project.get(pid, [])),
            )
        return result
