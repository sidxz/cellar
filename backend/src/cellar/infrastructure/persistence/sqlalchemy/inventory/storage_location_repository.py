"""SQLAlchemy repository for StorageLocation entities."""

from __future__ import annotations

import uuid

from sqlalchemy import delete, func, select

from cellar.domain.inventory.enums import StorageLocationType
from cellar.domain.inventory.storage_location import StorageLocation
from cellar.domain.shared.value_objects import Barcode
from cellar.infrastructure.persistence.sqlalchemy.base_repository import (
    SQLAlchemyRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.inventory.models import (
    SampleModel,
    StorageLocationModel,
)


class SQLAlchemyStorageLocationRepository(
    SQLAlchemyRepository[StorageLocation, StorageLocationModel]
):
    model_class = StorageLocationModel

    async def find_by_workspace(
        self,
        workspace_id: uuid.UUID,
        *,
        cursor_id: uuid.UUID | None = None,
        limit: int | None = None,
    ) -> list[StorageLocation]:
        stmt = (
            select(StorageLocationModel)
            .where(StorageLocationModel.workspace_id == workspace_id)
            .order_by(StorageLocationModel.id)
        )
        if cursor_id is not None:
            stmt = stmt.where(StorageLocationModel.id > cursor_id)
        if limit is not None:
            stmt = stmt.limit(limit)
        result = await self._session.execute(stmt)
        return [self._to_domain_tracked(m) for m in result.scalars().all()]

    async def find_children(
        self, workspace_id: uuid.UUID, parent_id: uuid.UUID
    ) -> list[StorageLocation]:
        stmt = (
            select(StorageLocationModel)
            .where(
                StorageLocationModel.workspace_id == workspace_id,
                StorageLocationModel.parent_id == parent_id,
            )
            .order_by(StorageLocationModel.name)
        )
        result = await self._session.execute(stmt)
        return [self._to_domain_tracked(m) for m in result.scalars().all()]

    async def find_by_workspace_with_counts(self, workspace_id: uuid.UUID) -> list[dict]:
        """Return all storage locations with available-sample counts."""
        # Subquery: count available samples per location
        sample_counts = (
            select(
                SampleModel.location_id,
                func.count().label("sample_count"),
            )
            .where(
                SampleModel.workspace_id == workspace_id,
                SampleModel.status == "available",
            )
            .group_by(SampleModel.location_id)
            .subquery()
        )

        stmt = (
            select(
                StorageLocationModel,
                func.coalesce(sample_counts.c.sample_count, 0).label("sample_count"),
            )
            .outerjoin(
                sample_counts,
                StorageLocationModel.id == sample_counts.c.location_id,
            )
            .where(StorageLocationModel.workspace_id == workspace_id)
            .order_by(StorageLocationModel.name)
        )
        result = await self._session.execute(stmt)
        rows: list[dict] = []
        for loc_model, count in result.all():
            rows.append(
                {
                    "id": loc_model.id,
                    "workspace_id": loc_model.workspace_id,
                    "name": loc_model.name,
                    "type": loc_model.type,
                    "parent_id": loc_model.parent_id,
                    "barcode": loc_model.barcode,
                    "temperature": loc_model.temperature,
                    "rows": loc_model.rows,
                    "columns": loc_model.columns,
                    "capacity": loc_model.capacity,
                    "sample_count": count,
                }
            )
        return rows

    async def delete(self, workspace_id: uuid.UUID, id: uuid.UUID) -> None:
        stmt = delete(StorageLocationModel).where(
            StorageLocationModel.workspace_id == workspace_id,
            StorageLocationModel.id == id,
        )
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

    def _update_model(self, model: StorageLocationModel, aggregate: StorageLocation) -> None:
        model.name = aggregate.name
        model.type = aggregate.type.value
        model.parent_id = aggregate.parent_id
        model.parent_type = aggregate.parent_type.value if aggregate.parent_type else None
        model.barcode = aggregate.barcode.value if aggregate.barcode else None
        model.temperature = aggregate.temperature
        model.rows = aggregate.rows
        model.columns = aggregate.columns
        model.capacity = aggregate.capacity
