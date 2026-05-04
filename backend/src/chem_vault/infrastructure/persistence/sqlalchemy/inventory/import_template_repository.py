"""SQLAlchemy repository for ImportTemplate entities.

ImportTemplate is not an AggregateRoot — standalone repo with manual CRUD.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select

from chem_vault.domain.inventory.import_template import ImportTemplate
from chem_vault.infrastructure.persistence.sqlalchemy.inventory.models import (
    ImportTemplateModel,
)
from chem_vault.infrastructure.persistence.unit_of_work import AsyncUnitOfWork


class SQLAlchemyImportTemplateRepository:
    """Persists ImportTemplate entities to PostgreSQL."""

    def __init__(self, uow: AsyncUnitOfWork) -> None:
        self._uow = uow

    async def find_by_id(self, id: uuid.UUID) -> ImportTemplate | None:
        model = await self._uow.session.get(ImportTemplateModel, id)
        return self._to_domain(model) if model else None

    async def find_by_id_in_workspace(
        self, workspace_id: uuid.UUID, id: uuid.UUID
    ) -> ImportTemplate | None:
        """Load by PK scoped to workspace."""
        stmt = (
            select(ImportTemplateModel)
            .where(
                ImportTemplateModel.id == id,
                ImportTemplateModel.workspace_id == workspace_id,
            )
        )
        result = await self._uow.session.execute(stmt)
        model = result.scalar_one_or_none()
        if model is None:
            return None
        return self._to_domain(model)

    async def find_by_workspace(
        self, workspace_id: uuid.UUID
    ) -> list[ImportTemplate]:
        stmt = (
            select(ImportTemplateModel)
            .where(ImportTemplateModel.workspace_id == workspace_id)
            .order_by(ImportTemplateModel.name)
        )
        result = await self._uow.session.execute(stmt)
        return [self._to_domain(m) for m in result.scalars().all()]

    async def save(self, entity: ImportTemplate) -> None:
        existing = await self._uow.session.get(ImportTemplateModel, entity.id)
        if existing is not None:
            if existing.workspace_id != entity.workspace_id:
                from chem_vault.domain.shared.errors import AuthorizationError
                raise AuthorizationError("Cannot update ImportTemplate from a different workspace")
            self._update_model(existing, entity)
        else:
            model = self._to_model(entity)
            self._uow.session.add(model)

    @staticmethod
    def _update_model(model: ImportTemplateModel, entity: ImportTemplate) -> None:
        model.name = entity.name
        model.description = entity.description
        model.column_mappings = entity.column_mappings
        model.default_protocol_id = entity.default_protocol_id

    async def delete(self, workspace_id: uuid.UUID, id: uuid.UUID) -> None:
        model = await self._uow.session.get(ImportTemplateModel, id)
        if model is not None and model.workspace_id == workspace_id:
            await self._uow.session.delete(model)

    # ------------------------------------------------------------------
    # Mapping
    # ------------------------------------------------------------------

    @staticmethod
    def _to_domain(model: ImportTemplateModel) -> ImportTemplate:
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

    @staticmethod
    def _to_model(entity: ImportTemplate) -> ImportTemplateModel:
        return ImportTemplateModel(
            id=entity.id,
            workspace_id=entity.workspace_id,
            name=entity.name,
            description=entity.description,
            column_mappings=entity.column_mappings,
            default_protocol_id=entity.default_protocol_id,
            created_by=entity.created_by,
        )
