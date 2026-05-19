"""SQLAlchemy repository for ImportTemplate entities.

ImportTemplate is a plain Entity (no version, no domain events). Inherits the
workspace-scoped read/save/delete surface from ``EntityRepository``.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select

from cellar.domain.inventory.import_template import ImportTemplate
from cellar.infrastructure.persistence.sqlalchemy.base_repository import (
    EntityRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.inventory.models import (
    ImportTemplateModel,
)


class SQLAlchemyImportTemplateRepository(
    EntityRepository[ImportTemplate, ImportTemplateModel]
):
    """Persists ImportTemplate entities to PostgreSQL."""

    model_class = ImportTemplateModel

    async def find_by_workspace(  # type: ignore[override]
        self, workspace_id: uuid.UUID
    ) -> list[ImportTemplate]:
        """Override the base to order by name (chemist-friendly listing)."""
        stmt = (
            select(ImportTemplateModel)
            .where(ImportTemplateModel.workspace_id == workspace_id)
            .order_by(ImportTemplateModel.name)
        )
        result = await self._session.execute(stmt)
        return [self._to_domain(m) for m in result.scalars().all()]

    def _to_domain(self, model: ImportTemplateModel) -> ImportTemplate:
        return ImportTemplate(
            id=model.id,
            workspace_id=model.workspace_id,
            name=model.name,
            description=model.description,
            column_mappings=model.column_mappings,
            default_protocol_id=model.default_protocol_id,
            created_by=model.created_by,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    def _to_model(self, entity: ImportTemplate) -> ImportTemplateModel:
        return ImportTemplateModel(
            id=entity.id,
            workspace_id=entity.workspace_id,
            name=entity.name,
            description=entity.description,
            column_mappings=entity.column_mappings,
            default_protocol_id=entity.default_protocol_id,
            created_by=entity.created_by,
        )

    def _update_model(self, model: ImportTemplateModel, entity: ImportTemplate) -> None:
        model.name = entity.name
        model.description = entity.description
        model.column_mappings = entity.column_mappings
        model.default_protocol_id = entity.default_protocol_id
