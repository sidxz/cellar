"""SQLAlchemy repository for PlateTemplate entities.

PlateTemplate is not an AggregateRoot — standalone repo with manual CRUD.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select

from chem_vault.domain.screening_assay.enums import PlateFormat
from chem_vault.domain.screening_assay.plate_template import PlateTemplate
from chem_vault.infrastructure.persistence.sqlalchemy.screening_assay.models import (
    PlateTemplateModel,
)
from chem_vault.infrastructure.persistence.unit_of_work import AsyncUnitOfWork


class SQLAlchemyPlateTemplateRepository:
    """Persists PlateTemplate entities to PostgreSQL."""

    def __init__(self, uow: AsyncUnitOfWork) -> None:
        self._uow = uow

    async def find_by_id(self, id: uuid.UUID) -> PlateTemplate | None:
        model = await self._uow.session.get(PlateTemplateModel, id)
        return self._to_domain(model) if model else None

    async def find_by_workspace(
        self, workspace_id: uuid.UUID
    ) -> list[PlateTemplate]:
        stmt = (
            select(PlateTemplateModel)
            .where(PlateTemplateModel.workspace_id == workspace_id)
            .order_by(PlateTemplateModel.name)
        )
        result = await self._uow.session.execute(stmt)
        return [self._to_domain(m) for m in result.scalars().all()]

    async def save(self, entity: PlateTemplate) -> None:
        model = self._to_model(entity)
        await self._uow.session.merge(model)

    async def delete(self, id: uuid.UUID) -> None:
        model = await self._uow.session.get(PlateTemplateModel, id)
        if model is not None:
            await self._uow.session.delete(model)

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
