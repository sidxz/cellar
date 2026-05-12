"""SQLAlchemy repository for PlateTemplate entities.

PlateTemplate is not an AggregateRoot — standalone repo with manual CRUD.
"""

from __future__ import annotations

import uuid

from sqlalchemy import func, select

from cellar.domain.screening_assay.enums import PlateFormat
from cellar.domain.screening_assay.plate_template import PlateTemplate
from cellar.infrastructure.persistence.sqlalchemy.screening_assay.models import (
    PlateTemplateModel,
)
from cellar.infrastructure.persistence.unit_of_work import AsyncUnitOfWork


class SQLAlchemyPlateTemplateRepository:
    """Persists PlateTemplate entities to PostgreSQL."""

    def __init__(self, uow: AsyncUnitOfWork) -> None:
        self._uow = uow

    async def _find_by_id_unscoped(self, id: uuid.UUID) -> PlateTemplate | None:
        model = await self._uow.session.get(PlateTemplateModel, id)
        return self._to_domain(model) if model else None

    async def find_by_id_in_workspace(
        self, workspace_id: uuid.UUID, id: uuid.UUID
    ) -> PlateTemplate | None:
        """Load by PK scoped to workspace."""
        stmt = select(PlateTemplateModel).where(
            PlateTemplateModel.id == id,
            PlateTemplateModel.workspace_id == workspace_id,
        )
        result = await self._uow.session.execute(stmt)
        model = result.scalar_one_or_none()
        if model is None:
            return None
        return self._to_domain(model)

    async def find_by_workspace(self, workspace_id: uuid.UUID) -> list[PlateTemplate]:
        stmt = (
            select(PlateTemplateModel)
            .where(PlateTemplateModel.workspace_id == workspace_id)
            .order_by(PlateTemplateModel.name)
        )
        result = await self._uow.session.execute(stmt)
        return [self._to_domain(m) for m in result.scalars().all()]

    async def save(self, entity: PlateTemplate) -> None:
        existing = await self._uow.session.get(PlateTemplateModel, entity.id)
        if existing is None:
            model = self._to_model(entity)
            self._uow.session.add(model)
        else:
            if existing.workspace_id != entity.workspace_id:
                from cellar.domain.shared.errors import AuthorizationError

                raise AuthorizationError("Cannot update PlateTemplate from a different workspace")
            self._update_model(existing, entity)

    async def delete(self, workspace_id: uuid.UUID, id: uuid.UUID) -> None:
        model = await self._uow.session.get(PlateTemplateModel, id)
        if model is not None and model.workspace_id == workspace_id:
            await self._uow.session.delete(model)

    async def count_references(self, workspace_id: uuid.UUID, template_id: uuid.UUID) -> int:
        """Count how many plates/runs reference this template within the workspace."""
        from cellar.infrastructure.persistence.sqlalchemy.screening_assay.models import (
            PlateModel,
            RunModel,
        )
        from cellar.infrastructure.persistence.sqlalchemy.inventory.models import (
            RegisteredPlateModel,
        )

        # PlateModel has no workspace_id — join through RunModel for workspace scoping
        run_result = await self._uow.session.execute(
            select(func.count())
            .select_from(PlateModel)
            .join(RunModel, PlateModel.run_id == RunModel.id)
            .where(
                PlateModel.template_id == template_id,
                RunModel.workspace_id == workspace_id,
            )
        )
        plate_result = await self._uow.session.execute(
            select(func.count())
            .select_from(RegisteredPlateModel)
            .where(
                RegisteredPlateModel.template_id == template_id,
                RegisteredPlateModel.workspace_id == workspace_id,
            )
        )
        return (run_result.scalar() or 0) + (plate_result.scalar() or 0)

    # ------------------------------------------------------------------
    # Mapping
    # ------------------------------------------------------------------

    @staticmethod
    def _to_domain(model: PlateTemplateModel) -> PlateTemplate:
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

    @staticmethod
    def _to_model(entity: PlateTemplate) -> PlateTemplateModel:
        return PlateTemplateModel(
            id=entity.id,
            workspace_id=entity.workspace_id,
            name=entity.name,
            format=entity.format.value,
            template_map=entity.template_map,
            description=entity.description,
            created_by=entity.created_by,
        )

    @staticmethod
    def _update_model(model: PlateTemplateModel, entity: PlateTemplate) -> None:
        model.name = entity.name
        model.format = entity.format.value
        model.template_map = entity.template_map
        model.description = entity.description
        model.created_by = entity.created_by
