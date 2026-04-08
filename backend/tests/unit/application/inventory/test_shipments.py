"""Tests for Shipment use cases."""

from __future__ import annotations

import uuid
from datetime import date
from types import TracebackType
from typing import Self

import pytest
from returns.result import Failure, Success

from tests.fakes.fake_auth import FakeAuth

from chem_vault.application.inventory.shipments import (
    AddShipmentItemCommand,
    CreateShipment,
    CreateShipmentCommand,
    DeliverShipment,
    DeliverShipmentCommand,
    GetShipment,
    GetShipmentQuery,
    ListShipments,
    ListShipmentsQuery,
    MarkInTransitCommand,
    MarkShipmentInTransit,
    ReturnShipment,
    ReturnShipmentCommand,
    ShipShipment,
    ShipShipmentCommand,
    ShipmentItemInput,
    AddShipmentItem,
)
from chem_vault.domain.inventory.enums import ShipmentStatus
from chem_vault.domain.inventory.shipment import Shipment, ShipmentItem
from chem_vault.domain.shared.enums import AmountUnit
from chem_vault.domain.shared.errors import NotFoundError
from chem_vault.domain.shared.events import DomainEvent
from chem_vault.domain.shared.value_objects import Amount

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

WS = uuid.uuid4()
OTHER_WS = uuid.uuid4()


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class FakeShipmentRepo:
    def __init__(self, items: list[Shipment] | None = None) -> None:
        self._store: dict[uuid.UUID, Shipment] = {
            item.id: item for item in (items or [])
        }

    async def find_by_id(self, id: uuid.UUID) -> Shipment | None:
        return self._store.get(id)

    async def find_by_id_in_workspace(
        self, workspace_id: uuid.UUID, id: uuid.UUID
    ) -> Shipment | None:
        item = self._store.get(id)
        if item is not None and item.workspace_id == workspace_id:
            return item
        return None

    async def find_by_workspace(
        self, workspace_id: uuid.UUID, *, status: str | None = None
    ) -> list[Shipment]:
        results = [s for s in self._store.values() if s.workspace_id == workspace_id]
        if status:
            results = [s for s in results if s.status.value == status]
        return results

    async def save(self, aggregate: Shipment) -> None:
        self._store[aggregate.id] = aggregate


class FakeUoW:
    async def commit(self) -> list[DomainEvent]:
        return []

    async def rollback(self) -> None:
        pass

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        pass


class FakeDispatcher:
    def __init__(self) -> None:
        self.dispatched: list[DomainEvent] = []

    async def dispatch_all(self, events: list[DomainEvent]) -> None:
        self.dispatched.extend(events)

    async def dispatch(self, event: DomainEvent) -> None:
        self.dispatched.append(event)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_shipment(workspace_id: uuid.UUID = WS) -> Shipment:
    """Create a test Shipment in PREPARING status."""
    item = ShipmentItem(
        shipment_id=uuid.uuid4(),
        sample_id=uuid.uuid4(),
        amount_shipped=Amount(value=5.0, unit=AmountUnit.MG),
    )
    shipment = Shipment.create(
        workspace_id=workspace_id,
        destination_org_id=uuid.uuid4(),
        sender_id=uuid.uuid4(),
        items=[item],
    )
    for i in shipment._items:
        i.shipment_id = shipment.id
    shipment.clear_events()
    return shipment


def _make_shipped_shipment(workspace_id: uuid.UUID = WS) -> Shipment:
    """Create a test Shipment in SHIPPED status."""
    shipment = _make_shipment(workspace_id)
    shipment.ship("TRACK-001")
    shipment.clear_events()
    return shipment


def _make_in_transit_shipment(workspace_id: uuid.UUID = WS) -> Shipment:
    """Create a test Shipment in IN_TRANSIT status."""
    shipment = _make_shipped_shipment(workspace_id)
    shipment.mark_in_transit()
    shipment.clear_events()
    return shipment


# ---------------------------------------------------------------------------
# CreateShipment tests
# ---------------------------------------------------------------------------


class TestCreateShipment:
    @pytest.mark.asyncio
    async def test_creates_shipment_with_items(self) -> None:
        repo = FakeShipmentRepo()
        uow = FakeUoW()
        dispatcher = FakeDispatcher()
        uc = CreateShipment(uow, repo, dispatcher)

        auth = FakeAuth(workspace_id=WS)
        cmd = CreateShipmentCommand(
            workspace_id=WS,
            sender_id=uuid.uuid4(),
            destination_org_id=uuid.uuid4(),
            items=[
                ShipmentItemInput(
                    sample_id=uuid.uuid4(),
                    amount_value=10.0,
                    amount_unit="mg",
                )
            ],
        )

        result = await uc(cmd, auth)

        assert isinstance(result, Success)
        shipment = result.unwrap()
        assert shipment.workspace_id == WS
        assert shipment.status == ShipmentStatus.PREPARING
        assert len(shipment.items) == 1
        assert shipment.id in repo._store

    @pytest.mark.asyncio
    async def test_item_shipment_id_fixed_after_creation(self) -> None:
        repo = FakeShipmentRepo()
        uow = FakeUoW()
        dispatcher = FakeDispatcher()
        uc = CreateShipment(uow, repo, dispatcher)

        auth = FakeAuth(workspace_id=WS)
        cmd = CreateShipmentCommand(
            workspace_id=WS,
            sender_id=uuid.uuid4(),
            destination_org_id=uuid.uuid4(),
            items=[
                ShipmentItemInput(
                    sample_id=uuid.uuid4(),
                    amount_value=5.0,
                    amount_unit="mg",
                )
            ],
        )

        result = await uc(cmd, auth)

        assert isinstance(result, Success)
        shipment = result.unwrap()
        for item in shipment.items:
            assert item.shipment_id == shipment.id

    @pytest.mark.asyncio
    async def test_creates_shipment_with_optional_fields(self) -> None:
        repo = FakeShipmentRepo()
        uow = FakeUoW()
        dispatcher = FakeDispatcher()
        uc = CreateShipment(uow, repo, dispatcher)

        auth = FakeAuth(workspace_id=WS)
        cmd = CreateShipmentCommand(
            workspace_id=WS,
            sender_id=uuid.uuid4(),
            destination_org_id=uuid.uuid4(),
            carrier="FedEx",
            expected_arrival_date=date(2026, 5, 1),
            shipping_conditions="Keep at -20C",
            notes="Handle with care",
            items=[
                ShipmentItemInput(
                    sample_id=uuid.uuid4(),
                    amount_value=2.5,
                    amount_unit="mL",
                )
            ],
        )

        result = await uc(cmd, auth)

        assert isinstance(result, Success)
        shipment = result.unwrap()
        assert shipment.carrier == "FedEx"
        assert shipment.notes == "Handle with care"
        assert shipment.shipping_conditions == "Keep at -20C"


# ---------------------------------------------------------------------------
# GetShipment tests
# ---------------------------------------------------------------------------


class TestGetShipment:
    @pytest.mark.asyncio
    async def test_get_found(self) -> None:
        shipment = _make_shipment()
        repo = FakeShipmentRepo([shipment])
        uow = FakeUoW()
        uc = GetShipment(uow, repo)

        auth = FakeAuth(workspace_id=WS)
        query = GetShipmentQuery(workspace_id=WS, shipment_id=shipment.id)

        result = await uc(query, auth)

        assert isinstance(result, Success)
        assert result.unwrap().id == shipment.id

    @pytest.mark.asyncio
    async def test_get_not_found(self) -> None:
        repo = FakeShipmentRepo()
        uow = FakeUoW()
        uc = GetShipment(uow, repo)

        auth = FakeAuth(workspace_id=WS)
        query = GetShipmentQuery(workspace_id=WS, shipment_id=uuid.uuid4())

        result = await uc(query, auth)

        assert isinstance(result, Failure)
        assert isinstance(result.failure(), NotFoundError)

    @pytest.mark.asyncio
    async def test_get_wrong_workspace_returns_failure(self) -> None:
        shipment = _make_shipment(workspace_id=OTHER_WS)
        repo = FakeShipmentRepo([shipment])
        uow = FakeUoW()
        uc = GetShipment(uow, repo)

        auth = FakeAuth(workspace_id=WS)
        query = GetShipmentQuery(workspace_id=WS, shipment_id=shipment.id)

        result = await uc(query, auth)
        assert isinstance(result, Failure)


# ---------------------------------------------------------------------------
# ListShipments tests
# ---------------------------------------------------------------------------


class TestListShipments:
    @pytest.mark.asyncio
    async def test_list_by_workspace(self) -> None:
        s1 = _make_shipment(workspace_id=WS)
        s2 = _make_shipment(workspace_id=WS)
        s3 = _make_shipment(workspace_id=OTHER_WS)
        repo = FakeShipmentRepo([s1, s2, s3])
        uow = FakeUoW()
        uc = ListShipments(uow, repo)

        auth = FakeAuth(workspace_id=WS)
        query = ListShipmentsQuery(workspace_id=WS)

        result = await uc(query, auth)

        assert isinstance(result, Success)
        ids = {s.id for s in result.unwrap()}
        assert s1.id in ids
        assert s2.id in ids
        assert s3.id not in ids

    @pytest.mark.asyncio
    async def test_list_with_status_filter(self) -> None:
        preparing = _make_shipment(workspace_id=WS)
        shipped = _make_shipped_shipment(workspace_id=WS)
        repo = FakeShipmentRepo([preparing, shipped])
        uow = FakeUoW()
        uc = ListShipments(uow, repo)

        auth = FakeAuth(workspace_id=WS)
        query = ListShipmentsQuery(workspace_id=WS, status="shipped")

        result = await uc(query, auth)

        assert isinstance(result, Success)
        results = result.unwrap()
        assert len(results) == 1
        assert results[0].id == shipped.id

    @pytest.mark.asyncio
    async def test_list_empty_workspace(self) -> None:
        repo = FakeShipmentRepo()
        uow = FakeUoW()
        uc = ListShipments(uow, repo)

        auth = FakeAuth(workspace_id=WS)
        query = ListShipmentsQuery(workspace_id=WS)

        result = await uc(query, auth)

        assert isinstance(result, Success)
        assert result.unwrap() == []


# ---------------------------------------------------------------------------
# ShipShipment tests
# ---------------------------------------------------------------------------


class TestShipShipment:
    @pytest.mark.asyncio
    async def test_ships_with_tracking_number(self) -> None:
        shipment = _make_shipment()
        repo = FakeShipmentRepo([shipment])
        uow = FakeUoW()
        dispatcher = FakeDispatcher()
        uc = ShipShipment(uow, repo, dispatcher)

        auth = FakeAuth(workspace_id=WS)
        cmd = ShipShipmentCommand(
            workspace_id=WS,
            shipment_id=shipment.id,
            tracking_number="TRACK-XYZ-001",
        )

        result = await uc(cmd, auth)

        assert isinstance(result, Success)
        updated = result.unwrap()
        assert updated.status == ShipmentStatus.SHIPPED
        assert updated.tracking_number == "TRACK-XYZ-001"

    @pytest.mark.asyncio
    async def test_ship_not_found(self) -> None:
        repo = FakeShipmentRepo()
        uow = FakeUoW()
        dispatcher = FakeDispatcher()
        uc = ShipShipment(uow, repo, dispatcher)

        auth = FakeAuth(workspace_id=WS)
        cmd = ShipShipmentCommand(
            workspace_id=WS,
            shipment_id=uuid.uuid4(),
            tracking_number="TRACK-001",
        )

        result = await uc(cmd, auth)

        assert isinstance(result, Failure)
        assert isinstance(result.failure(), NotFoundError)

    @pytest.mark.asyncio
    async def test_ship_with_date(self) -> None:
        shipment = _make_shipment()
        repo = FakeShipmentRepo([shipment])
        uow = FakeUoW()
        dispatcher = FakeDispatcher()
        uc = ShipShipment(uow, repo, dispatcher)

        auth = FakeAuth(workspace_id=WS)
        shipping_date = date(2026, 4, 10)
        cmd = ShipShipmentCommand(
            workspace_id=WS,
            shipment_id=shipment.id,
            tracking_number="TRACK-002",
            shipping_date=shipping_date,
        )

        result = await uc(cmd, auth)

        assert isinstance(result, Success)
        assert result.unwrap().shipping_date == shipping_date


# ---------------------------------------------------------------------------
# MarkShipmentInTransit tests
# ---------------------------------------------------------------------------


class TestMarkShipmentInTransit:
    @pytest.mark.asyncio
    async def test_marks_shipped_as_in_transit(self) -> None:
        shipment = _make_shipped_shipment()
        repo = FakeShipmentRepo([shipment])
        uow = FakeUoW()
        dispatcher = FakeDispatcher()
        uc = MarkShipmentInTransit(uow, repo, dispatcher)

        auth = FakeAuth(workspace_id=WS)
        cmd = MarkInTransitCommand(workspace_id=WS, shipment_id=shipment.id)

        result = await uc(cmd, auth)

        assert isinstance(result, Success)
        assert result.unwrap().status == ShipmentStatus.IN_TRANSIT

    @pytest.mark.asyncio
    async def test_mark_in_transit_not_found(self) -> None:
        repo = FakeShipmentRepo()
        uow = FakeUoW()
        dispatcher = FakeDispatcher()
        uc = MarkShipmentInTransit(uow, repo, dispatcher)

        auth = FakeAuth(workspace_id=WS)
        cmd = MarkInTransitCommand(workspace_id=WS, shipment_id=uuid.uuid4())

        result = await uc(cmd, auth)

        assert isinstance(result, Failure)
        assert isinstance(result.failure(), NotFoundError)


# ---------------------------------------------------------------------------
# DeliverShipment tests
# ---------------------------------------------------------------------------


class TestDeliverShipment:
    @pytest.mark.asyncio
    async def test_delivers_in_transit_shipment(self) -> None:
        shipment = _make_in_transit_shipment()
        repo = FakeShipmentRepo([shipment])
        uow = FakeUoW()
        dispatcher = FakeDispatcher()
        uc = DeliverShipment(uow, repo, dispatcher)

        auth = FakeAuth(workspace_id=WS)
        cmd = DeliverShipmentCommand(workspace_id=WS, shipment_id=shipment.id)

        result = await uc(cmd, auth)

        assert isinstance(result, Success)
        assert result.unwrap().status == ShipmentStatus.DELIVERED

    @pytest.mark.asyncio
    async def test_delivers_with_received_date(self) -> None:
        shipment = _make_in_transit_shipment()
        repo = FakeShipmentRepo([shipment])
        uow = FakeUoW()
        dispatcher = FakeDispatcher()
        uc = DeliverShipment(uow, repo, dispatcher)

        auth = FakeAuth(workspace_id=WS)
        received = date(2026, 4, 20)
        cmd = DeliverShipmentCommand(workspace_id=WS, shipment_id=shipment.id, received_date=received)

        result = await uc(cmd, auth)

        assert isinstance(result, Success)
        assert result.unwrap().received_date == received

    @pytest.mark.asyncio
    async def test_deliver_not_found(self) -> None:
        repo = FakeShipmentRepo()
        uow = FakeUoW()
        dispatcher = FakeDispatcher()
        uc = DeliverShipment(uow, repo, dispatcher)

        auth = FakeAuth(workspace_id=WS)
        cmd = DeliverShipmentCommand(workspace_id=WS, shipment_id=uuid.uuid4())

        result = await uc(cmd, auth)

        assert isinstance(result, Failure)
        assert isinstance(result.failure(), NotFoundError)


# ---------------------------------------------------------------------------
# ReturnShipment tests
# ---------------------------------------------------------------------------


class TestReturnShipment:
    @pytest.mark.asyncio
    async def test_returns_in_transit_shipment(self) -> None:
        shipment = _make_in_transit_shipment()
        repo = FakeShipmentRepo([shipment])
        uow = FakeUoW()
        dispatcher = FakeDispatcher()
        uc = ReturnShipment(uow, repo, dispatcher)

        auth = FakeAuth(workspace_id=WS)
        cmd = ReturnShipmentCommand(workspace_id=WS, shipment_id=shipment.id)

        result = await uc(cmd, auth)

        assert isinstance(result, Success)
        assert result.unwrap().status == ShipmentStatus.RETURNED

    @pytest.mark.asyncio
    async def test_return_not_found(self) -> None:
        repo = FakeShipmentRepo()
        uow = FakeUoW()
        dispatcher = FakeDispatcher()
        uc = ReturnShipment(uow, repo, dispatcher)

        auth = FakeAuth(workspace_id=WS)
        cmd = ReturnShipmentCommand(workspace_id=WS, shipment_id=uuid.uuid4())

        result = await uc(cmd, auth)

        assert isinstance(result, Failure)
        assert isinstance(result.failure(), NotFoundError)


# ---------------------------------------------------------------------------
# AddShipmentItem tests
# ---------------------------------------------------------------------------


class TestAddShipmentItem:
    @pytest.mark.asyncio
    async def test_adds_item_to_preparing_shipment(self) -> None:
        shipment = _make_shipment()
        initial_count = len(shipment.items)
        repo = FakeShipmentRepo([shipment])
        uow = FakeUoW()
        dispatcher = FakeDispatcher()
        uc = AddShipmentItem(uow, repo, dispatcher)

        auth = FakeAuth(workspace_id=WS)
        new_sample_id = uuid.uuid4()
        cmd = AddShipmentItemCommand(
            workspace_id=WS,
            shipment_id=shipment.id,
            sample_id=new_sample_id,
            amount_value=3.0,
            amount_unit="mg",
        )

        result = await uc(cmd, auth)

        assert isinstance(result, Success)
        updated = result.unwrap()
        assert len(updated.items) == initial_count + 1
        new_items = [i for i in updated.items if i.sample_id == new_sample_id]
        assert len(new_items) == 1
        assert new_items[0].amount_shipped.value == 3.0
        assert new_items[0].shipment_id == shipment.id

    @pytest.mark.asyncio
    async def test_add_item_not_found(self) -> None:
        repo = FakeShipmentRepo()
        uow = FakeUoW()
        dispatcher = FakeDispatcher()
        uc = AddShipmentItem(uow, repo, dispatcher)

        auth = FakeAuth(workspace_id=WS)
        cmd = AddShipmentItemCommand(
            workspace_id=WS,
            shipment_id=uuid.uuid4(),
            sample_id=uuid.uuid4(),
            amount_value=1.0,
            amount_unit="mg",
        )

        result = await uc(cmd, auth)

        assert isinstance(result, Failure)
        assert isinstance(result.failure(), NotFoundError)

    @pytest.mark.asyncio
    async def test_add_item_to_shipped_shipment_raises_domain_error(self) -> None:
        shipment = _make_shipped_shipment()
        repo = FakeShipmentRepo([shipment])
        uow = FakeUoW()
        dispatcher = FakeDispatcher()
        uc = AddShipmentItem(uow, repo, dispatcher)

        auth = FakeAuth(workspace_id=WS)
        cmd = AddShipmentItemCommand(
            workspace_id=WS,
            shipment_id=shipment.id,
            sample_id=uuid.uuid4(),
            amount_value=1.0,
            amount_unit="mg",
        )

        # Domain raises ValidationError — the use case doesn't catch it,
        # so it propagates as an exception
        with pytest.raises(Exception):
            await uc(cmd, auth)
