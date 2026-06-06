"""SQLAlchemy repository for Sample aggregates."""

from __future__ import annotations

import uuid

from sqlalchemy import or_, select

from cellar.domain.inventory.enums import ContainerType, SampleStatus
from cellar.domain.inventory.sample import Sample
from cellar.domain.shared.pagination import PageResult
from cellar.domain.shared.value_objects import Barcode
from cellar.infrastructure.persistence.sqlalchemy._sql import escape_like
from cellar.infrastructure.persistence.sqlalchemy.base_repository import (
    SQLAlchemyRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.chemical_registration.models import MoleculeModel
from cellar.infrastructure.persistence.sqlalchemy.inventory._vo_mappers import (
    amount_from_columns,
    amount_to_columns,
    concentration_from_columns,
    concentration_to_columns,
)
from cellar.infrastructure.persistence.sqlalchemy.inventory.models import (
    BatchModel,
    SampleModel,
    StorageLocationModel,
)


class SQLAlchemySampleRepository(SQLAlchemyRepository[Sample, SampleModel]):
    model_class = SampleModel

    async def find_by_batch(self, workspace_id: uuid.UUID, batch_id: uuid.UUID) -> list[Sample]:
        stmt = (
            select(SampleModel)
            .where(
                SampleModel.workspace_id == workspace_id,
                SampleModel.batch_id == batch_id,
            )
            .order_by(SampleModel.created_at.desc())
        )
        result = await self._session.execute(stmt)
        return [self._to_domain_tracked(m) for m in result.scalars().all()]

    async def find_by_location(
        self, workspace_id: uuid.UUID, location_id: uuid.UUID
    ) -> list[Sample]:
        stmt = (
            select(SampleModel)
            .where(
                SampleModel.workspace_id == workspace_id,
                SampleModel.location_id == location_id,
            )
            .order_by(SampleModel.barcode)
        )
        result = await self._session.execute(stmt)
        return [self._to_domain_tracked(m) for m in result.scalars().all()]

    async def find_by_barcode(self, workspace_id: uuid.UUID, barcode: str) -> Sample | None:
        stmt = select(SampleModel).where(
            SampleModel.workspace_id == workspace_id,
            SampleModel.barcode == barcode,
        )
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        return self._to_domain_tracked(model) if model else None

    async def find_low_stock(self, workspace_id: uuid.UUID) -> list[Sample]:
        stmt = (
            select(SampleModel)
            .where(
                SampleModel.workspace_id == workspace_id,
                SampleModel.status == SampleStatus.AVAILABLE.value,
                SampleModel.low_stock_threshold.isnot(None),
                SampleModel.amount_value < SampleModel.low_stock_threshold,
            )
            .order_by(SampleModel.amount_value)
        )
        result = await self._session.execute(stmt)
        return [self._to_domain_tracked(m) for m in result.scalars().all()]

    # ------------------------------------------------------------------
    # Global list (read-model query — returns flat dicts, not aggregates)
    # ------------------------------------------------------------------

    async def list_global(
        self,
        workspace_id: uuid.UUID,
        *,
        search: str | None = None,
        statuses: list[str] | None = None,
        location_id: uuid.UUID | None = None,
        container_types: list[str] | None = None,
        low_stock: bool = False,
        cursor: uuid.UUID | None = None,
        limit: int = 50,
    ) -> PageResult[dict]:
        stmt = (
            select(
                SampleModel.id,
                SampleModel.barcode,
                SampleModel.batch_id,
                BatchModel.batch_number,
                BatchModel.molecule_id,
                MoleculeModel.name.label("molecule_name"),
                MoleculeModel.registration_number.label("molecule_registration_number"),
                SampleModel.container_type,
                SampleModel.amount_value,
                SampleModel.amount_unit,
                SampleModel.status,
                SampleModel.solvent,
                SampleModel.freeze_thaw_count,
                SampleModel.low_stock_threshold,
                SampleModel.location_id,
                StorageLocationModel.name.label("location_name"),
                StorageLocationModel.type.label("location_type"),
                SampleModel.created_at,
            )
            .join(BatchModel, SampleModel.batch_id == BatchModel.id)
            .join(MoleculeModel, BatchModel.molecule_id == MoleculeModel.id)
            .outerjoin(StorageLocationModel, SampleModel.location_id == StorageLocationModel.id)
            .where(SampleModel.workspace_id == workspace_id)
        )

        # --- filters ---
        if search:
            pattern = f"%{escape_like(search)}%"
            stmt = stmt.where(
                or_(
                    SampleModel.barcode.ilike(pattern),
                    MoleculeModel.name.ilike(pattern),
                    MoleculeModel.registration_number.ilike(pattern),
                    BatchModel.batch_number.ilike(pattern),
                )
            )

        if statuses:
            stmt = stmt.where(SampleModel.status.in_(statuses))

        if location_id is not None:
            stmt = stmt.where(SampleModel.location_id == location_id)

        if container_types:
            stmt = stmt.where(SampleModel.container_type.in_(container_types))

        if low_stock:
            stmt = stmt.where(
                SampleModel.status == SampleStatus.AVAILABLE.value,
                SampleModel.low_stock_threshold.isnot(None),
                SampleModel.amount_value < SampleModel.low_stock_threshold,
            )

        # --- cursor pagination (keyset on created_at DESC, id DESC) ---
        if cursor is not None:
            cursor_sub = (
                select(SampleModel.created_at).where(SampleModel.id == cursor).scalar_subquery()
            )
            stmt = stmt.where(
                (SampleModel.created_at < cursor_sub)
                | ((SampleModel.created_at == cursor_sub) & (SampleModel.id < cursor))
            )

        stmt = stmt.order_by(SampleModel.created_at.desc(), SampleModel.id.desc())

        # Fetch limit + 1 to detect next page
        stmt = stmt.limit(limit + 1)

        result = await self._session.execute(stmt)
        rows = result.mappings().all()

        has_next = len(rows) > limit
        page_rows = rows[:limit]

        items = [dict(row) for row in page_rows]
        next_cursor = str(items[-1]["id"]) if has_next and items else None

        return PageResult(items=items, next_cursor=next_cursor)

    # ------------------------------------------------------------------
    # Mapping
    # ------------------------------------------------------------------

    def _to_domain(self, model: SampleModel) -> Sample:
        return Sample(
            id=model.id,
            workspace_id=model.workspace_id,
            batch_id=model.batch_id,
            barcode=Barcode(value=model.barcode),
            container_type=ContainerType(model.container_type),
            amount=amount_from_columns(model),
            concentration=concentration_from_columns(model),
            solvent=model.solvent,
            status=SampleStatus(model.status),
            location_id=model.location_id,
            freeze_thaw_count=model.freeze_thaw_count,
            low_stock_threshold=model.low_stock_threshold,
            created_at=model.created_at,
            updated_at=model.updated_at,
            version=model.version,
        )

    def _to_model(self, aggregate: Sample) -> SampleModel:
        return SampleModel(
            id=aggregate.id,
            workspace_id=aggregate.workspace_id,
            batch_id=aggregate.batch_id,
            barcode=aggregate.barcode.value,
            container_type=aggregate.container_type.value,
            **amount_to_columns(aggregate.amount),
            **concentration_to_columns(aggregate.concentration),
            solvent=aggregate.solvent,
            status=aggregate.status.value,
            location_id=aggregate.location_id,
            freeze_thaw_count=aggregate.freeze_thaw_count,
            low_stock_threshold=aggregate.low_stock_threshold,
            version=aggregate.version,
        )

    def _update_model(self, model: SampleModel, aggregate: Sample) -> None:
        for k, v in amount_to_columns(aggregate.amount).items():
            setattr(model, k, v)
        for k, v in concentration_to_columns(aggregate.concentration).items():
            setattr(model, k, v)
        model.solvent = aggregate.solvent
        model.status = aggregate.status.value
        model.location_id = aggregate.location_id
        model.freeze_thaw_count = aggregate.freeze_thaw_count
        model.low_stock_threshold = aggregate.low_stock_threshold
