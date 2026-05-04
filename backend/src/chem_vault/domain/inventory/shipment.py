"""Shipment aggregate — chain-of-custody for external sample shipping."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime

from chem_vault.domain.inventory.enums import ShipmentStatus
from chem_vault.domain.inventory.events import (
    ShipmentCreated,
    ShipmentDelivered,
    ShipmentShipped,
)
from chem_vault.domain.shared.entity import AggregateRoot, Entity
from chem_vault.domain.shared.errors import ValidationError
from chem_vault.domain.shared.value_objects import Amount


# ---------------------------------------------------------------------------
# ShipmentItem — owned entity
# ---------------------------------------------------------------------------


class ShipmentItem(Entity):
    """An individual sample included in a shipment."""

    def __init__(
        self,
        *,
        id: uuid.UUID | None = None,
        shipment_id: uuid.UUID,
        sample_id: uuid.UUID,
        amount_shipped: Amount,
        created_at: datetime | None = None,
        updated_at: datetime | None = None,
    ) -> None:
        super().__init__(id=id, created_at=created_at, updated_at=updated_at)
        self.shipment_id = shipment_id
        self.sample_id = sample_id
        self.amount_shipped = amount_shipped


# ---------------------------------------------------------------------------
# State machine
# ---------------------------------------------------------------------------


_VALID_TRANSITIONS: dict[ShipmentStatus, set[ShipmentStatus]] = {
    ShipmentStatus.PREPARING: {ShipmentStatus.SHIPPED},
    ShipmentStatus.SHIPPED: {ShipmentStatus.IN_TRANSIT},
    ShipmentStatus.IN_TRANSIT: {ShipmentStatus.DELIVERED, ShipmentStatus.RETURNED},
    # Terminal states
    ShipmentStatus.DELIVERED: set(),
    ShipmentStatus.RETURNED: set(),
}


# ---------------------------------------------------------------------------
# Shipment aggregate root
# ---------------------------------------------------------------------------


class Shipment(AggregateRoot):
    """Tracks chain-of-custody when samples are shipped externally."""

    def __init__(
        self,
        *,
        id: uuid.UUID | None = None,
        workspace_id: uuid.UUID,
        destination_org_id: uuid.UUID,
        sender_id: uuid.UUID,
        tracking_number: str | None = None,
        carrier: str | None = None,
        shipping_date: date | None = None,
        expected_arrival_date: date | None = None,
        received_date: date | None = None,
        shipping_conditions: str | None = None,
        status: ShipmentStatus = ShipmentStatus.PREPARING,
        notes: str | None = None,
        items: list[ShipmentItem] | None = None,
        created_at: datetime | None = None,
        updated_at: datetime | None = None,
        version: int = 1,
    ) -> None:
        super().__init__(id=id, created_at=created_at, updated_at=updated_at, version=version)
        self.workspace_id = workspace_id
        self.destination_org_id = destination_org_id
        self.sender_id = sender_id
        self.tracking_number = tracking_number
        self.carrier = carrier
        self.shipping_date = shipping_date
        self.expected_arrival_date = expected_arrival_date
        self.received_date = received_date
        self.shipping_conditions = shipping_conditions
        self.status = status
        self.notes = notes
        self._items: list[ShipmentItem] = list(items or [])

    @property
    def items(self) -> list[ShipmentItem]:
        return list(self._items)

    @classmethod
    def create(
        cls,
        *,
        workspace_id: uuid.UUID,
        destination_org_id: uuid.UUID,
        sender_id: uuid.UUID,
        carrier: str | None = None,
        expected_arrival_date: date | None = None,
        shipping_conditions: str | None = None,
        notes: str | None = None,
        items: list[ShipmentItem] | None = None,
    ) -> Shipment:
        if not items:
            raise ValidationError("A shipment must have at least one item")

        shipment = cls(
            workspace_id=workspace_id,
            destination_org_id=destination_org_id,
            sender_id=sender_id,
            carrier=carrier,
            expected_arrival_date=expected_arrival_date,
            shipping_conditions=shipping_conditions,
            notes=notes,
            items=items,
        )
        # Fix item references to point to the actual shipment ID
        for item in shipment._items:
            item.shipment_id = shipment.id
        shipment.register_event(
            ShipmentCreated(
                aggregate_id=shipment.id,
                aggregate_type="Shipment",
                workspace_id=workspace_id,
                destination_org_id=destination_org_id,
                item_count=len(items),
            )
        )
        return shipment

    # -- Item management --

    def add_item(self, item: ShipmentItem) -> None:
        if self.status != ShipmentStatus.PREPARING:
            raise ValidationError("Items can only be added to preparing shipments")
        self._items.append(item)
        self.updated_at = datetime.now(UTC)

    # -- Mutable field updates --

    def update_details(
        self,
        *,
        carrier: str | None = ...,  # type: ignore[assignment]
        expected_arrival_date: date | None = ...,  # type: ignore[assignment]
        shipping_conditions: str | None = ...,  # type: ignore[assignment]
        notes: str | None = ...,  # type: ignore[assignment]
    ) -> None:
        """Update mutable fields on a preparing shipment (sentinel pattern)."""
        if self.status != ShipmentStatus.PREPARING:
            raise ValidationError("Can only update shipments in preparing status")
        if carrier is not ...:
            self.carrier = carrier
        if expected_arrival_date is not ...:
            self.expected_arrival_date = expected_arrival_date
        if shipping_conditions is not ...:
            self.shipping_conditions = shipping_conditions
        if notes is not ...:
            self.notes = notes
        self.updated_at = datetime.now(UTC)

    # -- State transitions --

    def ship(self, tracking_number: str, shipping_date: date | None = None) -> None:
        self._assert_transition(ShipmentStatus.SHIPPED)
        if not tracking_number.strip():
            raise ValidationError("Tracking number is required to ship")
        self.tracking_number = tracking_number
        self.shipping_date = shipping_date or date.today()
        self.status = ShipmentStatus.SHIPPED
        self.updated_at = datetime.now(UTC)
        self.register_event(
            ShipmentShipped(
                aggregate_id=self.id,
                aggregate_type="Shipment",
                workspace_id=self.workspace_id,
                tracking_number=tracking_number,
            )
        )

    def mark_in_transit(self) -> None:
        self._assert_transition(ShipmentStatus.IN_TRANSIT)
        self.status = ShipmentStatus.IN_TRANSIT
        self.updated_at = datetime.now(UTC)

    def deliver(self, received_date: date | None = None) -> None:
        self._assert_transition(ShipmentStatus.DELIVERED)
        self.received_date = received_date or date.today()
        self.status = ShipmentStatus.DELIVERED
        self.updated_at = datetime.now(UTC)
        self.register_event(
            ShipmentDelivered(
                aggregate_id=self.id,
                aggregate_type="Shipment",
                workspace_id=self.workspace_id,
                received_date=self.received_date.isoformat(),
            )
        )

    def return_shipment(self) -> None:
        self._assert_transition(ShipmentStatus.RETURNED)
        self.status = ShipmentStatus.RETURNED
        self.updated_at = datetime.now(UTC)

    def _assert_transition(self, target: ShipmentStatus) -> None:
        allowed = _VALID_TRANSITIONS.get(self.status, set())
        if target not in allowed:
            raise ValidationError(
                f"Cannot transition from {self.status.value} to {target.value}"
            )
