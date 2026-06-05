"""SQLAlchemy repository for RunImportTemplate entities."""

from __future__ import annotations

import uuid

from sqlalchemy import select

from cellar.domain.screening_assay.run_import_template import RunImportTemplate
from cellar.infrastructure.persistence.sqlalchemy.base_repository import (
    EntityRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.screening_assay.models import (
    RunImportTemplateModel,
)


class SQLAlchemyRunImportTemplateRepository(
    EntityRepository[RunImportTemplate, RunImportTemplateModel]
):
    """Persists RunImportTemplate entities to PostgreSQL."""

    model_class = RunImportTemplateModel

    async def find_by_workspace(  # type: ignore[override]
        self, workspace_id: uuid.UUID
    ) -> list[RunImportTemplate]:
        """Override the base to order by name (chemist-friendly listing)."""
        stmt = (
            select(RunImportTemplateModel)
            .where(RunImportTemplateModel.workspace_id == workspace_id)
            .order_by(RunImportTemplateModel.name)
        )
        result = await self._session.execute(stmt)
        return [self._to_domain(m) for m in result.scalars().all()]

    def _to_domain(self, model: RunImportTemplateModel) -> RunImportTemplate:
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

    def _to_model(self, entity: RunImportTemplate) -> RunImportTemplateModel:
        return RunImportTemplateModel(
            id=entity.id,
            workspace_id=entity.workspace_id,
            name=entity.name,
            description=entity.description,
            column_mapping=entity.column_mapping,
            created_by=entity.created_by,
        )

    def _update_model(self, model: RunImportTemplateModel, entity: RunImportTemplate) -> None:
        model.name = entity.name
        model.description = entity.description
        model.column_mapping = entity.column_mapping
