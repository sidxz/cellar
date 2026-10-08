"""SQLAlchemy repository for NamingLabel aggregates."""

from __future__ import annotations

import uuid

from sqlalchemy import delete, select

from cellar.domain.workspace_config.naming_label import NamingLabel
from cellar.infrastructure.persistence.sqlalchemy.base_repository import (
    SQLAlchemyRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.workspace_config.models import (
    NamingLabelModel,
)


class SQLAlchemyNamingLabelRepository(SQLAlchemyRepository[NamingLabel, NamingLabelModel]):
    model_class = NamingLabelModel

    def _to_domain(self, model: NamingLabelModel) -> NamingLabel:
        return NamingLabel(
            id=model.id,
            workspace_id=model.workspace_id,
            term_id=model.term_id,
            term_label=model.term_label,
            ontology_source=model.ontology_source,
            short_label=model.short_label,
            created_at=model.created_at,
            updated_at=model.updated_at,
            version=model.version,
        )

    def _to_model(self, aggregate: NamingLabel) -> NamingLabelModel:
        return NamingLabelModel(
            id=aggregate.id,
            workspace_id=aggregate.workspace_id,
            term_id=aggregate.term_id,
            term_label=aggregate.term_label,
            ontology_source=aggregate.ontology_source,
            short_label=aggregate.short_label,
            version=aggregate.version,
        )

    def _update_model(self, model: NamingLabelModel, aggregate: NamingLabel) -> None:
        model.short_label = aggregate.short_label

    async def find_by_workspace(self, workspace_id: uuid.UUID) -> list[NamingLabel]:
        stmt = (
            select(NamingLabelModel)
            .where(NamingLabelModel.workspace_id == workspace_id)
            .order_by(NamingLabelModel.term_label)
        )
        result = await self._session.execute(stmt)
        return [self._to_domain_tracked(m) for m in result.scalars()]

    async def find_by_term(self, workspace_id: uuid.UUID, term_id: str) -> NamingLabel | None:
        stmt = select(NamingLabelModel).where(
            NamingLabelModel.workspace_id == workspace_id,
            NamingLabelModel.term_id == term_id,
        )
        model = (await self._session.execute(stmt)).scalar_one_or_none()
        return self._to_domain_tracked(model) if model else None

    async def delete(self, workspace_id: uuid.UUID, id: uuid.UUID) -> None:
        await self._session.execute(
            delete(NamingLabelModel).where(
                NamingLabelModel.workspace_id == workspace_id, NamingLabelModel.id == id
            )
        )
