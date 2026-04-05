"""SQLAlchemy repository for Shipment aggregates."""

from __future__ import annotations

import uuid

from sqlalchemy import select

from chem_vault.domain.inventory.enums import ShipmentStatus
from chem_vault.domain.inventory.shipment import Shipment, ShipmentItem
from chem_vault.domain.shared.enums import AmountUnit
from chem_vault.domain.shared.value_objects import Amount
from chem_vault.infrastructure.persistence.sqlalchemy.base_repository import (
    SQLAlchemyRepository,
)
from chem_vault.infrastructure.persistence.sqlalchemy.inventory.shipment_models import (
    ShipmentItemModel,
    ShipmentModel,
)


class SQLAlchemyShipmentRepository(
    SQLAlchemyRepository[Shipment, ShipmentModel]
):
    model_class = ShipmentModel

    async def find_by_workspace(
        self, workspace_id: uuid.UUID, *, status: str | None = None
    ) -> list[Shipment]:
        stmt = select(ShipmentModel).where(
            ShipmentModel.workspace_id == workspace_id
        )
        if status:
            stmt = stmt.where(ShipmentModel.status == status)
        stmt = stmt.order_by(ShipmentModel.created_at.desc())
        result = await self._session.execute(stmt)
        shipments = []
        for model in result.scalars().all():
            domain = self._to_domain(model)
            self._uow.track(domain)
            shipments.append(domain)
        return shipments

    def _to_domain(self, model: ShipmentModel) -> Shipment:
        items = [
            ShipmentItem(
                id=item.id,
                shipment_id=item.shipment_id,
                sample_id=item.sample_id,
                amount_shipped=Amount(
                    value=item.amount_shipped_value,
                    unit=AmountUnit(item.amount_shipped_unit),
                ),
                created_at=item.created_at,
                updated_at=item.updated_at,
            )
            for item in model.items
        ]

        return Shipment(
            id=model.id,
            workspace_id=model.workspace_id,
            destination_org_id=model.destination_org_id,
            sender_id=model.sender_id,
            tracking_number=model.tracking_number,
            carrier=model.carrier,
            shipping_date=model.shipping_date,
            expected_arrival_date=model.expected_arrival_date,
            received_date=model.received_date,
            shipping_conditions=model.shipping_conditions,
            status=ShipmentStatus(model.status),
            notes=model.notes,
            items=items,
            created_at=model.created_at,
            updated_at=model.updated_at,
            version=model.version,
        )

    def _to_model(self, aggregate: Shipment) -> ShipmentModel:
        model = ShipmentModel(
            id=aggregate.id,
            workspace_id=aggregate.workspace_id,
            destination_org_id=aggregate.destination_org_id,
            sender_id=aggregate.sender_id,
            tracking_number=aggregate.tracking_number,
            carrier=aggregate.carrier,
            shipping_date=aggregate.shipping_date,
            expected_arrival_date=aggregate.expected_arrival_date,
            received_date=aggregate.received_date,
            shipping_conditions=aggregate.shipping_conditions,
            status=aggregate.status.value,
            notes=aggregate.notes,
            version=aggregate.version,
        )
        model.items = [self._item_to_model(i) for i in aggregate.items]
        return model

    def _update_model(self, model: ShipmentModel, aggregate: Shipment) -> None:
        model.tracking_number = aggregate.tracking_number
        model.carrier = aggregate.carrier
        model.shipping_date = aggregate.shipping_date
        model.expected_arrival_date = aggregate.expected_arrival_date
        model.received_date = aggregate.received_date
        model.shipping_conditions = aggregate.shipping_conditions
        model.status = aggregate.status.value
        model.notes = aggregate.notes
        model.items = [self._item_to_model(i) for i in aggregate.items]

    @staticmethod
    def _item_to_model(item: ShipmentItem) -> ShipmentItemModel:
        return ShipmentItemModel(
            id=item.id,
            shipment_id=item.shipment_id,
            sample_id=item.sample_id,
            amount_shipped_value=item.amount_shipped.value,
            amount_shipped_unit=item.amount_shipped.unit.value,
        )
