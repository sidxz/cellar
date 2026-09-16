"""SQLAlchemy implementation of ShipmentsReader — item/loan → shipments, item labels."""

from __future__ import annotations

import uuid

from sqlalchemy import func, null, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from cellar.application.inventory.shipment_reads import ItemKey, ItemLabel, ShipmentLink
from cellar.domain.inventory.enums import ShipmentItemType
from cellar.infrastructure.persistence.sqlalchemy.inventory.models import (
    BatchModel,
    RegisteredPlateModel,
    SampleModel,
)
from cellar.infrastructure.persistence.sqlalchemy.inventory.shipment_models import (
    ShipmentItemModel,
    ShipmentModel,
)

# Column order == ShipmentLink field order up to the amount pair (rows are splatted).
_LINK_COLUMNS = (
    ShipmentModel.id,
    ShipmentModel.direction,
    ShipmentModel.status,
    ShipmentModel.destination_org_id,
    ShipmentModel.tracking_number,
    ShipmentModel.carrier,
    ShipmentModel.shipping_date,
    ShipmentModel.received_date,
)


class SQLAlchemyShipmentsReader:
    """Opens a fresh session per call — safe to register as a singleton."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def shipments_for_item(
        self, workspace_id: uuid.UUID, item_type: ShipmentItemType, item_id: uuid.UUID
    ) -> list[ShipmentLink]:
        stmt = (
            select(
                *_LINK_COLUMNS,
                ShipmentItemModel.amount_shipped_value,
                ShipmentItemModel.amount_shipped_unit,
                ShipmentModel.created_at,
            )
            .select_from(ShipmentItemModel)
            .join(ShipmentModel, ShipmentModel.id == ShipmentItemModel.shipment_id)
            .where(
                ShipmentItemModel.item_type == item_type.value,
                ShipmentItemModel.item_id == item_id,
                ShipmentModel.workspace_id == workspace_id,
            )
            .order_by(ShipmentModel.created_at.desc())
        )
        async with self._session_factory() as session:
            rows = (await session.execute(stmt)).all()
        return [ShipmentLink(*row) for row in rows]

    async def shipments_for_loan(
        self, workspace_id: uuid.UUID, loan_id: uuid.UUID
    ) -> list[ShipmentLink]:
        stmt = (
            select(*_LINK_COLUMNS, null(), null(), ShipmentModel.created_at)
            .where(ShipmentModel.loan_id == loan_id, ShipmentModel.workspace_id == workspace_id)
            .order_by(ShipmentModel.created_at.desc())
        )
        async with self._session_factory() as session:
            rows = (await session.execute(stmt)).all()
        return [ShipmentLink(*row) for row in rows]

    async def item_labels(
        self, workspace_id: uuid.UUID, plate_ids: list[uuid.UUID], sample_ids: list[uuid.UUID]
    ) -> dict[ItemKey, ItemLabel]:
        out: dict[ItemKey, ItemLabel] = {}
        async with self._session_factory() as session:
            if plate_ids:
                stmt = select(
                    RegisteredPlateModel.id,
                    RegisteredPlateModel.barcode,
                    RegisteredPlateModel.plate_label,
                ).where(
                    RegisteredPlateModel.id.in_(plate_ids),
                    RegisteredPlateModel.workspace_id == workspace_id,
                )
                for pid, barcode, label in (await session.execute(stmt)).all():
                    out[(ShipmentItemType.PLATE, pid)] = ItemLabel(barcode, label)
            if sample_ids:
                stmt = (
                    select(
                        SampleModel.id,
                        SampleModel.barcode,
                        func.coalesce(BatchModel.batch_number, SampleModel.barcode),
                    )
                    .join(BatchModel, BatchModel.id == SampleModel.batch_id, isouter=True)
                    .where(
                        SampleModel.id.in_(sample_ids),
                        SampleModel.workspace_id == workspace_id,
                    )
                )
                for sid, barcode, label in (await session.execute(stmt)).all():
                    out[(ShipmentItemType.SAMPLE, sid)] = ItemLabel(barcode, label)
        return out
