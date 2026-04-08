"""SQLAlchemy repository for ExternalApiKey aggregates."""

from __future__ import annotations

import uuid

from sqlalchemy import delete, select

from chem_vault.domain.workspace_config.external_api_key import ExternalApiKey
from chem_vault.infrastructure.persistence.sqlalchemy.base_repository import (
    SQLAlchemyRepository,
)
from chem_vault.infrastructure.persistence.sqlalchemy.workspace_config.models import (
    ExternalApiKeyModel,
)


class SQLAlchemyExternalApiKeyRepository(
    SQLAlchemyRepository[ExternalApiKey, ExternalApiKeyModel]
):
    model_class = ExternalApiKeyModel

    def _to_domain(self, model: ExternalApiKeyModel) -> ExternalApiKey:
        return ExternalApiKey(
            id=model.id,
            workspace_id=model.workspace_id,
            key_name=model.key_name,
            label=model.label,
            description=model.description,
            key_prefix=model.key_prefix,
            is_active=model.is_active,
            created_by=model.created_by,
            last_used_at=model.last_used_at,
            version=model.version,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    def _to_model(self, aggregate: ExternalApiKey) -> ExternalApiKeyModel:
        return ExternalApiKeyModel(
            id=aggregate.id,
            workspace_id=aggregate.workspace_id,
            key_name=aggregate.key_name,
            label=aggregate.label,
            description=aggregate.description,
            key_prefix=aggregate.key_prefix,
            is_active=aggregate.is_active,
            created_by=aggregate.created_by,
            last_used_at=aggregate.last_used_at,
            version=aggregate.version,
        )

    def _update_model(self, model: ExternalApiKeyModel, aggregate: ExternalApiKey) -> None:
        model.label = aggregate.label
        model.description = aggregate.description
        model.key_prefix = aggregate.key_prefix
        model.is_active = aggregate.is_active
        model.last_used_at = aggregate.last_used_at

    async def find_by_workspace(
        self,
        workspace_id: uuid.UUID,
    ) -> list[ExternalApiKey]:
        stmt = (
            select(ExternalApiKeyModel)
            .where(ExternalApiKeyModel.workspace_id == workspace_id)
            .order_by(ExternalApiKeyModel.key_name)
        )
        result = await self._session.execute(stmt)
        return [self._to_domain_tracked(m) for m in result.scalars()]

    async def find_by_key_name(
        self, workspace_id: uuid.UUID, key_name: str
    ) -> ExternalApiKey | None:
        stmt = select(ExternalApiKeyModel).where(
            ExternalApiKeyModel.workspace_id == workspace_id,
            ExternalApiKeyModel.key_name == key_name,
        )
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        return self._to_domain_tracked(model) if model else None

    async def delete(self, workspace_id: uuid.UUID, id: uuid.UUID) -> None:
        stmt = delete(ExternalApiKeyModel).where(
            ExternalApiKeyModel.workspace_id == workspace_id,
            ExternalApiKeyModel.id == id,
        )
        await self._session.execute(stmt)
