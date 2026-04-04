"""SQLAlchemy repository for StorageLocation entities."""

from __future__ import annotations

import uuid

from sqlalchemy import delete, select

from chem_vault.domain.inventory.enums import StorageLocationType
from chem_vault.domain.inventory.storage_location import StorageLocation
from chem_vault.domain.shared.value_objects import Barcode
from chem_vault.infrastructure.persistence.sqlalchemy.base_repository import (
    SQLAlchemyRepository,
)
from chem_vault.infrastructure.persistence.sqlalchemy.inventory.models import (
    StorageLocationModel,
)


class SQLAlchemyStorageLocationRepository(
    SQLAlchemyRepository[StorageLocation, StorageLocationModel]
):
    model_class = StorageLocationModel

    async def find_by_workspace(
        self, workspace_id: uuid.UUID
    ) -> list[StorageLocation]:
        stmt = (
            select(StorageLocationModel)
            .where(StorageLocationModel.workspace_id == workspace_id)
            .order_by(StorageLocationModel.name)
        )
        result = await self._session.execute(stmt)
        return [self._to_domain(m) for m in result.scalars().all()]

    async def find_children(self, parent_id: uuid.UUID) -> list[StorageLocation]:
        stmt = (
            select(StorageLocationModel)
            .where(StorageLocationModel.parent_id == parent_id)
            .order_by(StorageLocationModel.name)
        )
        result = await self._session.execute(stmt)
        return [self._to_domain(m) for m in result.scalars().all()]

    async def delete(self, id: uuid.UUID) -> None:
        stmt = delete(StorageLocationModel).where(StorageLocationModel.id == id)
        await self._session.execute(stmt)

    # ------------------------------------------------------------------
    # Mapping
    # ------------------------------------------------------------------

    def _to_domain(self, model: StorageLocationModel) -> StorageLocation:
        return StorageLocation(
            id=model.id,
            workspace_id=model.workspace_id,
            name=model.name,
            type=StorageLocationType(model.type),
            parent_id=model.parent_id,
            parent_type=StorageLocationType(model.parent_type) if model.parent_type else None,
            barcode=Barcode(value=model.barcode) if model.barcode else None,
            temperature=model.temperature,
            rows=model.rows,
            columns=model.columns,
            capacity=model.capacity,
            created_at=model.created_at,
            updated_at=model.updated_at,
            version=model.version,
        )

    def _to_model(self, aggregate: StorageLocation) -> StorageLocationModel:
        return StorageLocationModel(
            id=aggregate.id,
            workspace_id=aggregate.workspace_id,
            name=aggregate.name,
            type=aggregate.type.value,
            parent_id=aggregate.parent_id,
            parent_type=aggregate.parent_type.value if aggregate.parent_type else None,
            barcode=aggregate.barcode.value if aggregate.barcode else None,
            temperature=aggregate.temperature,
            rows=aggregate.rows,
            columns=aggregate.columns,
            capacity=aggregate.capacity,
            version=aggregate.version,
        )

    def _update_model(
        self, model: StorageLocationModel, aggregate: StorageLocation
    ) -> None:
        model.name = aggregate.name
        model.barcode = aggregate.barcode.value if aggregate.barcode else None
        model.temperature = aggregate.temperature
        model.rows = aggregate.rows
        model.columns = aggregate.columns
        model.capacity = aggregate.capacity
