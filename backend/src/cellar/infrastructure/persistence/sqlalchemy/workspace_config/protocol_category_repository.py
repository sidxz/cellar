"""SQLAlchemy repository for ProtocolCategory aggregates."""

from __future__ import annotations

import uuid

from sqlalchemy import delete, func, select

from cellar.domain.workspace_config.protocol_category import ProtocolCategory
from cellar.infrastructure.persistence.sqlalchemy.base_repository import (
    SQLAlchemyRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.workspace_config.models import (
    ProtocolCategoryModel,
)


class SQLAlchemyProtocolCategoryRepository(
    SQLAlchemyRepository[ProtocolCategory, ProtocolCategoryModel]
):
    model_class = ProtocolCategoryModel

    def _to_domain(self, model: ProtocolCategoryModel) -> ProtocolCategory:
        return ProtocolCategory(
            id=model.id,
            workspace_id=model.workspace_id,
            label=model.label,
            name_pattern=model.name_pattern,
            created_at=model.created_at,
            updated_at=model.updated_at,
            version=model.version,
        )

    def _to_model(self, aggregate: ProtocolCategory) -> ProtocolCategoryModel:
        return ProtocolCategoryModel(
            id=aggregate.id,
            workspace_id=aggregate.workspace_id,
            label=aggregate.label,
            name_pattern=aggregate.name_pattern,
            version=aggregate.version,
        )

    def _update_model(self, model: ProtocolCategoryModel, aggregate: ProtocolCategory) -> None:
        model.label = aggregate.label
        model.name_pattern = aggregate.name_pattern

    async def find_by_workspace(self, workspace_id: uuid.UUID) -> list[ProtocolCategory]:
        stmt = (
            select(ProtocolCategoryModel)
            .where(ProtocolCategoryModel.workspace_id == workspace_id)
            .order_by(ProtocolCategoryModel.label)
        )
        result = await self._session.execute(stmt)
        return [self._to_domain_tracked(m) for m in result.scalars()]

    async def find_by_label(self, workspace_id: uuid.UUID, label: str) -> ProtocolCategory | None:
        stmt = select(ProtocolCategoryModel).where(
            ProtocolCategoryModel.workspace_id == workspace_id,
            func.lower(ProtocolCategoryModel.label) == " ".join(label.split()).lower(),
        )
        model = (await self._session.execute(stmt)).scalar_one_or_none()
        return self._to_domain_tracked(model) if model else None

    async def delete(self, workspace_id: uuid.UUID, id: uuid.UUID) -> None:
        await self._session.execute(
            delete(ProtocolCategoryModel).where(
                ProtocolCategoryModel.workspace_id == workspace_id,
                ProtocolCategoryModel.id == id,
            )
        )
