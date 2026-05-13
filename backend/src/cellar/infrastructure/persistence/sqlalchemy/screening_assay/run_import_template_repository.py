"""SQLAlchemy repository for RunImportTemplate entities."""

from __future__ import annotations

import uuid

from sqlalchemy import select

from cellar.domain.screening_assay.run_import_template import RunImportTemplate
from cellar.domain.shared.errors import AuthorizationError
from cellar.infrastructure.persistence.sqlalchemy.screening_assay.models import (
    RunImportTemplateModel,
)
from cellar.infrastructure.persistence.unit_of_work import AsyncUnitOfWork


class SQLAlchemyRunImportTemplateRepository:
    """Persists RunImportTemplate entities to PostgreSQL."""

    def __init__(self, uow: AsyncUnitOfWork) -> None:
        self._uow = uow

    async def find_by_id_in_workspace(
        self, workspace_id: uuid.UUID, id: uuid.UUID
    ) -> RunImportTemplate | None:
        stmt = select(RunImportTemplateModel).where(
            RunImportTemplateModel.id == id,
            RunImportTemplateModel.workspace_id == workspace_id,
        )
        result = await self._uow.session.execute(stmt)
        model = result.scalar_one_or_none()
        return self._to_domain(model) if model else None

    async def find_by_workspace(self, workspace_id: uuid.UUID) -> list[RunImportTemplate]:
        stmt = (
            select(RunImportTemplateModel)
            .where(RunImportTemplateModel.workspace_id == workspace_id)
            .order_by(RunImportTemplateModel.name)
        )
        result = await self._uow.session.execute(stmt)
        return [self._to_domain(m) for m in result.scalars().all()]

    async def save(self, entity: RunImportTemplate) -> None:
        existing = await self._uow.session.get(RunImportTemplateModel, entity.id)
        if existing is not None:
            if existing.workspace_id != entity.workspace_id:
                raise AuthorizationError(
                    "Cannot update RunImportTemplate from a different workspace"
                )
            existing.name = entity.name
            existing.description = entity.description
            existing.column_mapping = entity.column_mapping
        else:
            self._uow.session.add(self._to_model(entity))

    async def delete(self, workspace_id: uuid.UUID, id: uuid.UUID) -> None:
        model = await self._uow.session.get(RunImportTemplateModel, id)
        if model is not None and model.workspace_id == workspace_id:
            await self._uow.session.delete(model)

    @staticmethod
    def _to_domain(model: RunImportTemplateModel) -> RunImportTemplate:
        return RunImportTemplate(
            id=model.id,
            workspace_id=model.workspace_id,
            name=model.name,
            description=model.description,
            column_mapping=model.column_mapping,
            created_by=model.created_by,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    @staticmethod
    def _to_model(entity: RunImportTemplate) -> RunImportTemplateModel:
        return RunImportTemplateModel(
            id=entity.id,
            workspace_id=entity.workspace_id,
            name=entity.name,
            description=entity.description,
            column_mapping=entity.column_mapping,
            created_by=entity.created_by,
        )
