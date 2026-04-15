"""SQLAlchemy repository for DataSource aggregates."""

from __future__ import annotations

import uuid

from sqlalchemy import delete, select

from chem_vault.domain.workspace_config.data_source import (
    DataSource,
    EntityMapping,
)
from chem_vault.infrastructure.persistence.sqlalchemy.base_repository import (
    SQLAlchemyRepository,
)
from chem_vault.infrastructure.persistence.sqlalchemy.workspace_config.models import (
    DataSourceModel,
)


class SQLAlchemyDataSourceRepository(
    SQLAlchemyRepository[DataSource, DataSourceModel]
):
    model_class = DataSourceModel

    # ------------------------------------------------------------------
    # Domain <-> Model conversion
    # ------------------------------------------------------------------

    def _to_domain(self, model: DataSourceModel) -> DataSource:
        return DataSource(
            id=model.id,
            workspace_id=model.workspace_id,
            name=model.name,
            source_type=model.source_type,
            config=dict(model.config) if model.config else {},
            api_key_name=model.api_key_name,
            is_active=model.is_active,
            entity_mappings=_mappings_to_domain(model.entity_mappings),
            created_by=model.created_by,
            version=model.version,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    def _to_model(self, aggregate: DataSource) -> DataSourceModel:
        return DataSourceModel(
            id=aggregate.id,
            workspace_id=aggregate.workspace_id,
            name=aggregate.name,
            source_type=aggregate.source_type,
            config=aggregate.config,
            api_key_name=aggregate.api_key_name,
            is_active=aggregate.is_active,
            entity_mappings=_mappings_to_json(aggregate.entity_mappings),
            created_by=aggregate.created_by,
            version=aggregate.version,
        )

    def _update_model(self, model: DataSourceModel, aggregate: DataSource) -> None:
        model.name = aggregate.name
        model.config = aggregate.config
        model.api_key_name = aggregate.api_key_name
        model.is_active = aggregate.is_active
        model.entity_mappings = _mappings_to_json(aggregate.entity_mappings)

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    async def find_by_workspace(
        self, workspace_id: uuid.UUID
    ) -> list[DataSource]:
        stmt = (
            select(DataSourceModel)
            .where(DataSourceModel.workspace_id == workspace_id)
            .order_by(DataSourceModel.name)
        )
        result = await self._session.execute(stmt)
        return [self._to_domain_tracked(m) for m in result.scalars()]

    async def find_by_name(
        self, workspace_id: uuid.UUID, name: str
    ) -> DataSource | None:
        stmt = select(DataSourceModel).where(
            DataSourceModel.workspace_id == workspace_id,
            DataSourceModel.name == name,
        )
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        return self._to_domain_tracked(model) if model else None

    async def find_active_by_source_type(
        self, workspace_id: uuid.UUID, source_type: str
    ) -> DataSource | None:
        stmt = select(DataSourceModel).where(
            DataSourceModel.workspace_id == workspace_id,
            DataSourceModel.source_type == source_type,
            DataSourceModel.is_active.is_(True),
        )
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        return self._to_domain_tracked(model) if model else None

    async def delete(self, workspace_id: uuid.UUID, id: uuid.UUID) -> None:
        stmt = delete(DataSourceModel).where(
            DataSourceModel.workspace_id == workspace_id,
            DataSourceModel.id == id,
        )
        await self._session.execute(stmt)


# ======================================================================
# JSONB <-> Domain dataclass helpers
# ======================================================================


def _mappings_to_domain(raw: list | None) -> list[EntityMapping]:
    if not raw:
        return []
    return [EntityMapping.from_dict(em) for em in raw]


def _mappings_to_json(mappings: list[EntityMapping]) -> list[dict]:
    return [em.to_dict() for em in mappings]
