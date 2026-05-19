"""SQLAlchemy repository for PlateTemplate entities.

PlateTemplate is a plain Entity (no version, no domain events). Inherits the
workspace-scoped read/save/delete surface from ``EntityRepository``; overrides
``find_by_workspace`` to order by name (chemist-friendly) and adds
``count_references`` for the admin delete-safety check.
"""

from __future__ import annotations

import uuid

from sqlalchemy import func, select

from cellar.domain.screening_assay.enums import PlateFormat
from cellar.domain.screening_assay.plate_template import PlateTemplate
from cellar.infrastructure.persistence.sqlalchemy.base_repository import (
    EntityRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.screening_assay.models import (
    PlateTemplateModel,
)


class SQLAlchemyPlateTemplateRepository(
    EntityRepository[PlateTemplate, PlateTemplateModel]
):
    """Persists PlateTemplate entities to PostgreSQL."""

    model_class = PlateTemplateModel

    async def find_by_workspace(  # type: ignore[override]
        self, workspace_id: uuid.UUID
    ) -> list[PlateTemplate]:
        """Override the base to order by name (chemist-friendly listing)."""
        stmt = (
            select(PlateTemplateModel)
            .where(PlateTemplateModel.workspace_id == workspace_id)
            .order_by(PlateTemplateModel.name)
        )
        result = await self._session.execute(stmt)
        return [self._to_domain(m) for m in result.scalars().all()]

    async def count_references(
        self, workspace_id: uuid.UUID, template_id: uuid.UUID
    ) -> int:
        """Count how many plates/runs reference this template within the workspace."""
        from cellar.infrastructure.persistence.sqlalchemy.inventory.models import (
            RegisteredPlateModel,
        )
        from cellar.infrastructure.persistence.sqlalchemy.screening_assay.models import (
            PlateModel,
            RunModel,
        )

        # PlateModel has no workspace_id — join through RunModel for workspace scoping
        run_result = await self._session.execute(
            select(func.count())
            .select_from(PlateModel)
            .join(RunModel, PlateModel.run_id == RunModel.id)
            .where(
                PlateModel.template_id == template_id,
                RunModel.workspace_id == workspace_id,
            )
        )
        plate_result = await self._session.execute(
            select(func.count())
            .select_from(RegisteredPlateModel)
            .where(
                RegisteredPlateModel.template_id == template_id,
                RegisteredPlateModel.workspace_id == workspace_id,
            )
        )
        return (run_result.scalar() or 0) + (plate_result.scalar() or 0)

    def _to_domain(self, model: PlateTemplateModel) -> PlateTemplate:
        return PlateTemplate(
            id=model.id,
            workspace_id=model.workspace_id,
            name=model.name,
            format=PlateFormat(model.format),
            template_map=model.template_map,
            description=model.description,
            created_by=model.created_by,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    def _to_model(self, entity: PlateTemplate) -> PlateTemplateModel:
        return PlateTemplateModel(
            id=entity.id,
            workspace_id=entity.workspace_id,
            name=entity.name,
            format=entity.format.value,
            template_map=entity.template_map,
            description=entity.description,
            created_by=entity.created_by,
        )

    def _update_model(self, model: PlateTemplateModel, entity: PlateTemplate) -> None:
        model.name = entity.name
        model.format = entity.format.value
        model.template_map = entity.template_map
        model.description = entity.description
        model.created_by = entity.created_by
