"""Tests for Shipment aggregate root."""

import uuid
from datetime import date

import pytest

from cellar.domain.inventory.enums import (
    ShipmentDirection,
    ShipmentItemType,
    ShipmentStatus,
)
from cellar.domain.inventory.events import (
    ShipmentCreated,
    ShipmentDelivered,
    ShipmentShipped,
)
from cellar.domain.inventory.shipment import Shipment, ShipmentItem
from cellar.domain.shared.enums import AmountUnit
from cellar.domain.shared.errors import ValidationError
from cellar.domain.shared.value_objects import Amount


@pytest.fixture
def ws_id() -> uuid.UUID:
    return uuid.uuid4()


def _make_item(shipment_id: uuid.UUID | None = None) -> ShipmentItem:
    return ShipmentItem(
        shipment_id=shipment_id or uuid.uuid4(),
        item_type=ShipmentItemType.SAMPLE,
        item_id=uuid.uuid4(),
        amount_shipped=Amount(value=1.0, unit=AmountUnit.MG),
    )


def _make_shipment(ws_id: uuid.UUID, **overrides) -> Shipment:
    sid = uuid.uuid4()
    defaults = dict(
        workspace_id=ws_id,
        destination_org_id=uuid.uuid4(),
        sender_id=uuid.uuid4(),
        items=[_make_item(sid)],
    )
    defaults.update(overrides)
    return Shipment.create(**defaults)


class TestShipmentItemInvariants:
    def test_sample_item_requires_amount(self):
        with pytest.raises(ValidationError, match="amount"):
            ShipmentItem(
                shipment_id=uuid.uuid4(),
                item_type=ShipmentItemType.SAMPLE,
                item_id=uuid.uuid4(),
            )

    def test_plate_item_rejects_amount(self):
        with pytest.raises(ValidationError, match="amount"):
            ShipmentItem(
                shipment_id=uuid.uuid4(),
                item_type=ShipmentItemType.PLATE,
                item_id=uuid.uuid4(),
                amount_shipped=Amount(value=1.0, unit=AmountUnit.MG),
            )

    def test_plate_item_without_amount(self):
        item = ShipmentItem(
            shipment_id=uuid.uuid4(),
            item_type=ShipmentItemType.PLATE,
            item_id=uuid.uuid4(),
        )
        assert item.item_type == ShipmentItemType.PLATE
        assert item.amount_shipped is None


class TestShipmentCreation:
    def test_create_basic(self, ws_id):
        shipment = _make_shipment(ws_id)
        assert shipment.status == ShipmentStatus.PREPARING
        assert len(shipment.items) == 1
        assert shipment.direction == ShipmentDirection.OUTBOUND
        assert shipment.loan_id is None


    def test_update_loan_id_set_clear_and_sentinel(self, ws_id):
        shipment = _make_shipment(ws_id)
        loan_id = uuid.uuid4()
        shipment.update_details(loan_id=loan_id)
        assert shipment.loan_id == loan_id
        shipment.update_details(carrier="FedEx")  # loan_id omitted -> untouched
        assert shipment.loan_id == loan_id
        shipment.update_details(loan_id=None)
        assert shipment.loan_id is None

    def test_create_emits_event(self, ws_id):
        shipment = _make_shipment(ws_id)
        events = shipment.collect_events()
        assert len(events) == 1
        assert isinstance(events[0], ShipmentCreated)
        assert events[0].item_count == 1

    def test_create_no_items_raises(self, ws_id):
        with pytest.raises(ValidationError, match="at least one"):
            Shipment.create(
                workspace_id=ws_id,
                destination_org_id=uuid.uuid4(),
                sender_id=uuid.uuid4(),
                items=[],
            )

    def test_add_item_while_preparing(self, ws_id):
        shipment = _make_shipment(ws_id)
        shipment.add_item(_make_item(shipment.id))
        assert len(shipment.items) == 2


class TestShipmentTransitions:
    def test_ship(self, ws_id):
        shipment = _make_shipment(ws_id)
        shipment.ship("FX-123456", shipping_date=date(2026, 4, 5))
        assert shipment.status == ShipmentStatus.SHIPPED
        assert shipment.tracking_number == "FX-123456"
        assert shipment.shipping_date == date(2026, 4, 5)
        assert any(isinstance(e, ShipmentShipped) for e in shipment.collect_events())

    def test_ship_requires_tracking(self, ws_id):
        shipment = _make_shipment(ws_id)
        with pytest.raises(ValidationError, match="Tracking"):
            shipment.ship("   ")

    def test_ship_then_in_transit(self, ws_id):
        shipment = _make_shipment(ws_id)
        shipment.ship("FX-123")
        shipment.mark_in_transit()
        assert shipment.status == ShipmentStatus.IN_TRANSIT

    def test_deliver(self, ws_id):
        shipment = _make_shipment(ws_id)
        shipment.ship("FX-123")
        shipment.mark_in_transit()
        shipment.deliver(received_date=date(2026, 4, 7))
        assert shipment.status == ShipmentStatus.DELIVERED
        assert shipment.received_date == date(2026, 4, 7)
        assert any(isinstance(e, ShipmentDelivered) for e in shipment.collect_events())

    def test_return(self, ws_id):
        shipment = _make_shipment(ws_id)
        shipment.ship("FX-123")
        shipment.mark_in_transit()
        shipment.return_shipment()
        assert shipment.status == ShipmentStatus.RETURNED

    def test_cannot_ship_twice(self, ws_id):
        shipment = _make_shipment(ws_id)
        shipment.ship("FX-123")
        with pytest.raises(ValidationError, match="Cannot transition"):
            shipment.ship("FX-456")

    def test_cannot_deliver_from_preparing(self, ws_id):
        shipment = _make_shipment(ws_id)
        with pytest.raises(ValidationError, match="Cannot transition"):
            shipment.deliver()

    def test_cannot_add_item_after_shipped(self, ws_id):
        shipment = _make_shipment(ws_id)
        shipment.ship("FX-123")
        with pytest.raises(ValidationError, match="preparing"):
            shipment.add_item(_make_item(shipment.id))

    def test_full_lifecycle(self, ws_id):
        shipment = _make_shipment(ws_id)
        shipment.ship("FX-123", shipping_date=date(2026, 4, 5))
        shipment.mark_in_transit()
        shipment.deliver(received_date=date(2026, 4, 7))
        assert shipment.status == ShipmentStatus.DELIVERED
        assert shipment.tracking_number == "FX-123"
        assert shipment.received_date == date(2026, 4, 7)
