"""SQLAlchemy repository for CollectionImportTemplate entities."""

from __future__ import annotations

import uuid

from sqlalchemy import select

from cellar.domain.research_organization.collection_import_template import (
    CollectionImportTemplate,
)
from cellar.infrastructure.persistence.sqlalchemy.base_repository import (
    EntityRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.research_organization.models import (
    CollectionImportTemplateModel,
)


def _hydrate_used_in_collections(raw: list | None) -> list[uuid.UUID]:
    """JSONB round-trips UUIDs as strings; rehydrate into uuid.UUID."""
    if not raw:
        return []
    out: list[uuid.UUID] = []
    for entry in raw:
        if isinstance(entry, uuid.UUID):
            out.append(entry)
        else:
            try:
                out.append(uuid.UUID(str(entry)))
            except (ValueError, TypeError):
                # Defensive: skip malformed entries rather than crash a read.
                continue
    return out


def _serialize_used_in_collections(entries: list[uuid.UUID]) -> list[str]:
    """Persist UUIDs as strings in JSONB (Postgres-side comparable + portable)."""
    return [str(x) for x in entries]


class SQLAlchemyCollectionImportTemplateRepository(
    EntityRepository[CollectionImportTemplate, CollectionImportTemplateModel]
):
    """Persists CollectionImportTemplate entities to PostgreSQL."""

    model_class = CollectionImportTemplateModel

    async def find_by_workspace(  # type: ignore[override]
        self, workspace_id: uuid.UUID
    ) -> list[CollectionImportTemplate]:
        """Override the base to order by name (chemist-friendly listing)."""
        stmt = (
            select(CollectionImportTemplateModel)
            .where(CollectionImportTemplateModel.workspace_id == workspace_id)
            .order_by(CollectionImportTemplateModel.name)
        )
        result = await self._session.execute(stmt)
        return [self._to_domain(m) for m in result.scalars().all()]

    def _to_domain(self, model: CollectionImportTemplateModel) -> CollectionImportTemplate:
        return CollectionImportTemplate(
            id=model.id,
            workspace_id=model.workspace_id,
            name=model.name,
            description=model.description,
            column_mapping=model.column_mapping,
            used_in_collections=_hydrate_used_in_collections(model.used_in_collections),
            created_by=model.created_by,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    def _to_model(self, entity: CollectionImportTemplate) -> CollectionImportTemplateModel:
        return CollectionImportTemplateModel(
            id=entity.id,
            workspace_id=entity.workspace_id,
            name=entity.name,
            description=entity.description,
            column_mapping=entity.column_mapping,
            used_in_collections=_serialize_used_in_collections(entity.used_in_collections),
            created_by=entity.created_by,
        )

    def _update_model(
        self,
        model: CollectionImportTemplateModel,
        entity: CollectionImportTemplate,
    ) -> None:
        model.name = entity.name
        model.description = entity.description
        model.column_mapping = entity.column_mapping
        model.used_in_collections = _serialize_used_in_collections(entity.used_in_collections)
