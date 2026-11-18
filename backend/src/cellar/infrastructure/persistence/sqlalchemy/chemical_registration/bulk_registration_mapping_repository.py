"""SQLAlchemy repository for saved bulk-registration column mappings."""

from __future__ import annotations

import uuid

from sqlalchemy import select

from cellar.domain.chemical_registration.bulk_registration_mapping import (
    BulkRegistrationMapping,
)
from cellar.infrastructure.persistence.sqlalchemy.base_repository import EntityRepository
from cellar.infrastructure.persistence.sqlalchemy.chemical_registration.models import (
    BulkRegistrationMappingModel,
)


class SQLAlchemyBulkRegistrationMappingRepository(
    EntityRepository[BulkRegistrationMapping, BulkRegistrationMappingModel]
):
    model_class = BulkRegistrationMappingModel

    async def find_by_workspace(  # type: ignore[override]
        self, workspace_id: uuid.UUID
    ) -> list[BulkRegistrationMapping]:
        stmt = (
            select(BulkRegistrationMappingModel)
            .where(BulkRegistrationMappingModel.workspace_id == workspace_id)
            .order_by(BulkRegistrationMappingModel.name)
        )
        result = await self._session.execute(stmt)
        return [self._to_domain(m) for m in result.scalars().all()]

    def _to_domain(self, model: BulkRegistrationMappingModel) -> BulkRegistrationMapping:
        return BulkRegistrationMapping(
            id=model.id,
            workspace_id=model.workspace_id,
            name=model.name,
            columns=list(model.columns or []),
            created_by=model.created_by,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    def _to_model(self, entity: BulkRegistrationMapping) -> BulkRegistrationMappingModel:
        return BulkRegistrationMappingModel(
            id=entity.id,
            workspace_id=entity.workspace_id,
            name=entity.name,
            columns=entity.columns,
            created_by=entity.created_by,
        )

    def _update_model(
        self, model: BulkRegistrationMappingModel, entity: BulkRegistrationMapping
    ) -> None:
        model.name = entity.name
        model.columns = entity.columns
