"""SQLAlchemy repository for SavedVisualization aggregates."""

from __future__ import annotations

import uuid
from collections.abc import Sequence

import structlog
from sqlalchemy import delete, false, or_, select

from cellar.domain.research_organization.enums import SearchVisibility
from cellar.domain.research_organization.saved_visualization import SavedVisualization
from cellar.domain.shared.errors import ValidationError
from cellar.infrastructure.persistence.sqlalchemy._sql import any_id
from cellar.infrastructure.persistence.sqlalchemy.base_repository import SQLAlchemyRepository
from cellar.infrastructure.persistence.sqlalchemy.research_organization.models import (
    SavedVisualizationModel,
)

M = SavedVisualizationModel
log = structlog.get_logger(__name__)


class SQLAlchemySavedVisualizationRepository(
    SQLAlchemyRepository[SavedVisualization, SavedVisualizationModel]
):
    model_class = SavedVisualizationModel

    def _to_domain(self, model: SavedVisualizationModel) -> SavedVisualization:
        # A deleted project nulls project_id: the view is its owner's again.
        visibility = SearchVisibility(model.visibility)
        if model.project_id is None:
            visibility = SearchVisibility.PRIVATE
        return SavedVisualization(
            id=model.id,
            workspace_id=model.workspace_id,
            name=model.name,
            description=model.description,
            source=dict(model.source),
            protocol_ids=list(model.protocol_ids),
            level=model.level,
            config=dict(model.config),
            visibility=visibility,
            project_id=model.project_id,
            created_by=model.created_by,
            created_at=model.created_at,
            updated_at=model.updated_at,
            version=model.version,
        )

    def _to_model(self, aggregate: SavedVisualization) -> SavedVisualizationModel:
        return SavedVisualizationModel(
            id=aggregate.id,
            workspace_id=aggregate.workspace_id,
            name=aggregate.name,
            description=aggregate.description,
            source=aggregate.source,
            protocol_ids=list(aggregate.protocol_ids),
            level=aggregate.level,
            config=aggregate.config,
            visibility=aggregate.visibility.value,
            project_id=aggregate.project_id,
            created_by=aggregate.created_by,
            version=aggregate.version,
        )

    def _update_model(self, model: SavedVisualizationModel, aggregate: SavedVisualization) -> None:
        model.name = aggregate.name
        model.description = aggregate.description
        model.source = aggregate.source
        model.protocol_ids = list(aggregate.protocol_ids)
        model.level = aggregate.level
        model.config = aggregate.config
        model.visibility = aggregate.visibility.value
        model.project_id = aggregate.project_id
        model.updated_at = aggregate.updated_at

    async def find_visible(
        self,
        workspace_id: uuid.UUID,
        user_id: uuid.UUID,
        *,
        project_ids: Sequence[uuid.UUID] | None,
        protocol_id: uuid.UUID | None = None,
    ) -> list[SavedVisualization]:
        if project_ids is None:
            in_project = M.project_id.is_not(None)
        elif project_ids:
            in_project = any_id(M.project_id, project_ids)
        else:
            in_project = false()
        stmt = select(M).where(
            M.workspace_id == workspace_id,
            or_(
                M.created_by == user_id,
                (M.visibility == SearchVisibility.PROJECT.value) & in_project,
            ),
        )
        if protocol_id is not None:
            stmt = stmt.where(M.protocol_ids.contains([protocol_id]))  # @>, uses the GIN index
        result = await self._session.execute(stmt.order_by(M.name, M.id))
        views: list[SavedVisualization] = []
        for model in result.scalars():
            try:
                views.append(self._to_domain_tracked(model))
            except ValidationError as exc:
                # One unreadable view must not hide the others; opening it says why.
                log.warning(
                    "saved_visualization.list_skipped",
                    view_id=str(model.id),
                    workspace_id=str(model.workspace_id),
                    reason=exc.message,
                )
        return views

    async def delete(self, workspace_id: uuid.UUID, id: uuid.UUID) -> None:
        await self._session.execute(delete(M).where(M.workspace_id == workspace_id, M.id == id))
