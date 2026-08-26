"""Tests for Shipment use cases (S17: polymorphic items, direction, loan link)."""

from __future__ import annotations

import uuid
from datetime import date
from types import SimpleNamespace, TracebackType
from typing import Self

import pytest
from returns.result import Failure, Success

from cellar.application.inventory.plate_visibility import PlateVisibilityService
from cellar.application.inventory.shipments import (
    AddShipmentItem,
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
    ShipmentItemInput,
    ShipShipment,
    ShipShipmentCommand,
    UpdateShipment,
    UpdateShipmentCommand,
)
from cellar.domain.inventory.enums import (
    PlateType,
    ShipmentDirection,
    ShipmentItemType,
    ShipmentStatus,
)
from cellar.domain.inventory.registered_plate import RegisteredPlate
from cellar.domain.inventory.shipment import Shipment, ShipmentItem
from cellar.domain.shared.enums import AmountUnit, PlateFormat
from cellar.domain.shared.errors import NotFoundError, ValidationError
from cellar.domain.shared.events import DomainEvent
from cellar.domain.shared.value_objects import Amount, Barcode
from tests.fakes.fake_auth import FakeAuth
from tests.fakes.fake_registered_plate_repository import FakeRegisteredPlateRepository

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

WS = uuid.uuid4()
OTHER_WS = uuid.uuid4()
ORG_A = uuid.uuid4()
ORG_B = uuid.uuid4()


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class FakeShipmentRepo:
    def __init__(self, items: list[Shipment] | None = None) -> None:
        self._store: dict[uuid.UUID, Shipment] = {item.id: item for item in (items or [])}

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


class FakeSampleRepo:
    def __init__(self, samples: list | None = None) -> None:
        self._store = {s.id: s for s in samples or []}

    async def find_by_id_in_workspace(self, workspace_id: uuid.UUID, id: uuid.UUID):
        s = self._store.get(id)
        return s if s is not None and s.workspace_id == workspace_id else None

    async def find_by_barcode(self, workspace_id: uuid.UUID, barcode: str):
        return next(
            (
                s
                for s in self._store.values()
                if s.workspace_id == workspace_id and s.barcode.value == barcode
            ),
            None,
        )


class FakeLoanRepo:
    def __init__(self, loans: list | None = None, borrowed: set[uuid.UUID] | None = None) -> None:
        self._store = {loan.id: loan for loan in loans or []}
        self._borrowed = borrowed or set()

    async def find_by_id_in_workspace(self, workspace_id: uuid.UUID, id: uuid.UUID):
        loan = self._store.get(id)
        return loan if loan is not None and loan.workspace_id == workspace_id else None

    async def borrowed_plate_ids(self, workspace_id: uuid.UUID, org_id: uuid.UUID):
        return self._borrowed


class FakeOrgDirectory:
    async def list_orgs(self):
        return [SimpleNamespace(id=ORG_A), SimpleNamespace(id=ORG_B)]


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


def _auth(*, role: str = "editor", org_id: uuid.UUID | None = ORG_A, ws: uuid.UUID = WS):
    return FakeAuth(role=role, workspace_id=ws, org_id=org_id)


def _sample(ws: uuid.UUID = WS, barcode: str = "S-1"):
    return SimpleNamespace(
        id=uuid.uuid4(), workspace_id=ws, batch_id=uuid.uuid4(), barcode=Barcode(value=barcode)
    )


def _plate(owner_org_id: uuid.UUID | None, ws: uuid.UUID = WS, barcode: str | None = None):
    return RegisteredPlate.register(
        workspace_id=ws,
        owner_org_id=owner_org_id,
        barcode=Barcode(value=barcode or f"PLT-{uuid.uuid4().hex[:8]}"),
        plate_label="Test Plate",
        format=PlateFormat.F96,
        plate_type=PlateType.ASSAY,
        registered_by=uuid.uuid4(),
    )


def _loan(owner: uuid.UUID, borrower: uuid.UUID, ws: uuid.UUID = WS):
    return SimpleNamespace(
        id=uuid.uuid4(), workspace_id=ws, owner_org_id=owner, borrower_org_id=borrower
    )


def _sample_input(sample, value: float | None = 10.0, unit: str | None = "mg"):
    return ShipmentItemInput(
        item_type=ShipmentItemType.SAMPLE,
        item_id=sample.id,
        amount_value=value,
        amount_unit=unit,
    )


def _plate_input(plate, value: float | None = None, unit: str | None = None):
    return ShipmentItemInput(
        item_type=ShipmentItemType.PLATE, item_id=plate.id, amount_value=value, amount_unit=unit
    )


def _deps(*, samples=(), plates=(), loans=(), borrowed=None):
    loan_repo = FakeLoanRepo(list(loans), borrowed)
    return {
        "sample_repo": FakeSampleRepo(list(samples)),
        "plate_repo": FakeRegisteredPlateRepository(list(plates)),
        "visibility": PlateVisibilityService(FakeOrgDirectory(), loan_repo),
        "loan_repo": loan_repo,
    }


def _create_uc(repo: FakeShipmentRepo | None = None, **deps) -> CreateShipment:
    return CreateShipment(FakeUoW(), repo or FakeShipmentRepo(), FakeDispatcher(), **_deps(**deps))


def _add_uc(repo: FakeShipmentRepo, **deps) -> AddShipmentItem:
    d = _deps(**deps)
    d.pop("loan_repo")
    return AddShipmentItem(FakeUoW(), repo, FakeDispatcher(), **d)


def _update_uc(repo: FakeShipmentRepo, **deps) -> UpdateShipment:
    d = _deps(**deps)
    return UpdateShipment(
        FakeUoW(), repo, FakeDispatcher(), loan_repo=d["loan_repo"], visibility=d["visibility"]
    )


def _make_shipment(workspace_id: uuid.UUID = WS) -> Shipment:
    """Create a test Shipment in PREPARING status with one sample item."""
    item = ShipmentItem(
        shipment_id=uuid.uuid4(),
        item_type=ShipmentItemType.SAMPLE,
        item_id=uuid.uuid4(),
        amount_shipped=Amount(value=5.0, unit=AmountUnit.MG),
    )
    shipment = Shipment.create(
        workspace_id=workspace_id,
        destination_org_id=uuid.uuid4(),
        sender_id=uuid.uuid4(),
        items=[item],
    )
    shipment.clear_events()
    return shipment


def _make_shipped_shipment(workspace_id: uuid.UUID = WS) -> Shipment:
    shipment = _make_shipment(workspace_id)
    shipment.ship("TRACK-001")
    shipment.clear_events()
    return shipment


def _make_in_transit_shipment(workspace_id: uuid.UUID = WS) -> Shipment:
    shipment = _make_shipped_shipment(workspace_id)
    shipment.mark_in_transit()
    shipment.clear_events()
    return shipment


def _create_cmd(*items: ShipmentItemInput, **overrides) -> CreateShipmentCommand:
    return CreateShipmentCommand(
        workspace_id=WS,
        sender_id=uuid.uuid4(),
        destination_org_id=uuid.uuid4(),
        items=list(items),
        **overrides,
    )


# ---------------------------------------------------------------------------
# CreateShipment tests
# ---------------------------------------------------------------------------


class TestCreateShipment:
    async def test_creates_shipment_with_sample_item(self) -> None:
        sample = _sample()
        repo = FakeShipmentRepo()
        uc = _create_uc(repo, samples=[sample])

        result = await uc(_create_cmd(_sample_input(sample)), _auth())

        assert isinstance(result, Success)
        shipment = result.unwrap()
        assert shipment.workspace_id == WS
        assert shipment.status == ShipmentStatus.PREPARING
        assert shipment.direction == ShipmentDirection.OUTBOUND
        assert shipment.loan_id is None
        assert len(shipment.items) == 1
        assert shipment.items[0].item_type == ShipmentItemType.SAMPLE
        assert shipment.items[0].item_id == sample.id
        assert shipment.items[0].amount_shipped == Amount(value=10.0, unit=AmountUnit.MG)
        assert shipment.id in repo._store

    async def test_item_shipment_id_fixed_after_creation(self) -> None:
        sample = _sample()
        uc = _create_uc(samples=[sample])

        result = await uc(_create_cmd(_sample_input(sample)), _auth())

        shipment = result.unwrap()
        for item in shipment.items:
            assert item.shipment_id == shipment.id

    async def test_creates_shipment_with_optional_fields(self) -> None:
        sample = _sample()
        uc = _create_uc(samples=[sample])

        result = await uc(
            _create_cmd(
                _sample_input(sample, 2.5, "mL"),
                carrier="FedEx",
                expected_arrival_date=date(2026, 5, 1),
                shipping_conditions="Keep at -20C",
                notes="Handle with care",
            ),
            _auth(),
        )

        shipment = result.unwrap()
        assert shipment.carrier == "FedEx"
        assert shipment.notes == "Handle with care"
        assert shipment.shipping_conditions == "Keep at -20C"

    async def test_mixed_inbound_shipment_with_loan(self) -> None:
        sample = _sample()
        plate = _plate(ORG_A)
        loan = _loan(ORG_A, ORG_B)
        uc = _create_uc(samples=[sample], plates=[plate], loans=[loan])

        result = await uc(
            _create_cmd(
                _plate_input(plate),
                _sample_input(sample),
                direction=ShipmentDirection.INBOUND,
                loan_id=loan.id,
            ),
            _auth(),
        )

        assert isinstance(result, Success)
        shipment = result.unwrap()
        assert shipment.direction == ShipmentDirection.INBOUND
        assert shipment.loan_id == loan.id
        assert [i.item_type for i in shipment.items] == [
            ShipmentItemType.PLATE,
            ShipmentItemType.SAMPLE,
        ]
        assert shipment.items[0].amount_shipped is None

    async def test_unknown_sample_is_not_found(self) -> None:
        uc = _create_uc()

        result = await uc(_create_cmd(_sample_input(_sample())), _auth())

        assert isinstance(result, Failure)
        assert isinstance(result.failure(), NotFoundError)

    async def test_hidden_plate_is_not_found(self) -> None:
        plate = _plate(ORG_B)
        uc = _create_uc(plates=[plate])

        result = await uc(_create_cmd(_plate_input(plate)), _auth(org_id=ORG_A))

        assert isinstance(result, Failure)
        assert isinstance(result.failure(), NotFoundError)

    async def test_borrowed_plate_can_ship(self) -> None:
        plate = _plate(ORG_B)
        uc = _create_uc(plates=[plate], borrowed={plate.id})

        result = await uc(_create_cmd(_plate_input(plate)), _auth(org_id=ORG_A))

        assert isinstance(result, Success)

    async def test_sample_item_without_amount_is_validation_error(self) -> None:
        sample = _sample()
        uc = _create_uc(samples=[sample])

        result = await uc(_create_cmd(_sample_input(sample, None, None)), _auth())

        assert isinstance(result, Failure)
        assert isinstance(result.failure(), ValidationError)

    async def test_plate_item_with_amount_is_validation_error(self) -> None:
        plate = _plate(ORG_A)
        uc = _create_uc(plates=[plate])

        result = await uc(_create_cmd(_plate_input(plate, 1.0, "mg")), _auth())

        assert isinstance(result, Failure)
        assert isinstance(result.failure(), ValidationError)

    async def test_unknown_loan_is_not_found(self) -> None:
        sample = _sample()
        uc = _create_uc(samples=[sample])

        result = await uc(_create_cmd(_sample_input(sample), loan_id=uuid.uuid4()), _auth())

        assert isinstance(result, Failure)
        assert isinstance(result.failure(), NotFoundError)

    async def test_hidden_loan_is_not_found(self) -> None:
        sample = _sample()
        loan = _loan(ORG_B, ORG_B)
        uc = _create_uc(samples=[sample], loans=[loan])

        result = await uc(_create_cmd(_sample_input(sample), loan_id=loan.id), _auth(org_id=ORG_A))

        assert isinstance(result, Failure)
        assert isinstance(result.failure(), NotFoundError)

    async def test_borrower_sees_private_owner_loan(self) -> None:
        sample = _sample()
        loan = _loan(ORG_B, ORG_A)
        uc = _create_uc(samples=[sample], loans=[loan])

        result = await uc(_create_cmd(_sample_input(sample), loan_id=loan.id), _auth(org_id=ORG_A))

        assert isinstance(result, Success)


# ---------------------------------------------------------------------------
# GetShipment tests
# ---------------------------------------------------------------------------


class TestGetShipment:
    async def test_get_found(self) -> None:
        shipment = _make_shipment()
        uc = GetShipment(FakeUoW(), FakeShipmentRepo([shipment]))

        result = await uc(GetShipmentQuery(workspace_id=WS, shipment_id=shipment.id), _auth())

        assert isinstance(result, Success)
        assert result.unwrap().id == shipment.id

    async def test_get_not_found(self) -> None:
        uc = GetShipment(FakeUoW(), FakeShipmentRepo())

        result = await uc(GetShipmentQuery(workspace_id=WS, shipment_id=uuid.uuid4()), _auth())

        assert isinstance(result, Failure)
        assert isinstance(result.failure(), NotFoundError)

    async def test_get_wrong_workspace_returns_failure(self) -> None:
        shipment = _make_shipment(workspace_id=OTHER_WS)
        uc = GetShipment(FakeUoW(), FakeShipmentRepo([shipment]))

        result = await uc(GetShipmentQuery(workspace_id=WS, shipment_id=shipment.id), _auth())

        assert isinstance(result, Failure)


# ---------------------------------------------------------------------------
# ListShipments tests
# ---------------------------------------------------------------------------


class TestListShipments:
    async def test_list_by_workspace(self) -> None:
        s1 = _make_shipment(workspace_id=WS)
        s2 = _make_shipment(workspace_id=WS)
        s3 = _make_shipment(workspace_id=OTHER_WS)
        uc = ListShipments(FakeUoW(), FakeShipmentRepo([s1, s2, s3]))

        result = await uc(ListShipmentsQuery(workspace_id=WS), _auth())

        ids = {s.id for s in result.unwrap()}
        assert ids == {s1.id, s2.id}

    async def test_list_with_status_filter(self) -> None:
        preparing = _make_shipment(workspace_id=WS)
        shipped = _make_shipped_shipment(workspace_id=WS)
        uc = ListShipments(FakeUoW(), FakeShipmentRepo([preparing, shipped]))

        result = await uc(ListShipmentsQuery(workspace_id=WS, status="shipped"), _auth())

        results = result.unwrap()
        assert len(results) == 1
        assert results[0].id == shipped.id

    async def test_list_empty_workspace(self) -> None:
        uc = ListShipments(FakeUoW(), FakeShipmentRepo())

        result = await uc(ListShipmentsQuery(workspace_id=WS), _auth())

        assert result.unwrap() == []


# ---------------------------------------------------------------------------
# Lifecycle tests
# ---------------------------------------------------------------------------


class TestShipShipment:
    async def test_ships_with_tracking_number(self) -> None:
        shipment = _make_shipment()
        uc = ShipShipment(FakeUoW(), FakeShipmentRepo([shipment]), FakeDispatcher())

        result = await uc(
            ShipShipmentCommand(
                workspace_id=WS, shipment_id=shipment.id, tracking_number="TRACK-XYZ-001"
            ),
            _auth(),
        )

        updated = result.unwrap()
        assert updated.status == ShipmentStatus.SHIPPED
        assert updated.tracking_number == "TRACK-XYZ-001"

    async def test_ship_not_found(self) -> None:
        uc = ShipShipment(FakeUoW(), FakeShipmentRepo(), FakeDispatcher())

        result = await uc(
            ShipShipmentCommand(
                workspace_id=WS, shipment_id=uuid.uuid4(), tracking_number="TRACK-001"
            ),
            _auth(),
        )

        assert isinstance(result, Failure)
        assert isinstance(result.failure(), NotFoundError)

    async def test_ship_with_date(self) -> None:
        shipment = _make_shipment()
        uc = ShipShipment(FakeUoW(), FakeShipmentRepo([shipment]), FakeDispatcher())
        shipping_date = date(2026, 4, 10)

        result = await uc(
            ShipShipmentCommand(
                workspace_id=WS,
                shipment_id=shipment.id,
                tracking_number="TRACK-002",
                shipping_date=shipping_date,
            ),
            _auth(),
        )

        assert result.unwrap().shipping_date == shipping_date


class TestMarkShipmentInTransit:
    async def test_marks_shipped_as_in_transit(self) -> None:
        shipment = _make_shipped_shipment()
        uc = MarkShipmentInTransit(FakeUoW(), FakeShipmentRepo([shipment]), FakeDispatcher())

        result = await uc(MarkInTransitCommand(workspace_id=WS, shipment_id=shipment.id), _auth())

        assert result.unwrap().status == ShipmentStatus.IN_TRANSIT

    async def test_mark_in_transit_not_found(self) -> None:
        uc = MarkShipmentInTransit(FakeUoW(), FakeShipmentRepo(), FakeDispatcher())

        result = await uc(MarkInTransitCommand(workspace_id=WS, shipment_id=uuid.uuid4()), _auth())

        assert isinstance(result, Failure)
        assert isinstance(result.failure(), NotFoundError)


class TestDeliverShipment:
    async def test_delivers_in_transit_shipment(self) -> None:
        shipment = _make_in_transit_shipment()
        uc = DeliverShipment(FakeUoW(), FakeShipmentRepo([shipment]), FakeDispatcher())

        result = await uc(
            DeliverShipmentCommand(workspace_id=WS, shipment_id=shipment.id), _auth()
        )

        assert result.unwrap().status == ShipmentStatus.DELIVERED

    async def test_delivers_with_received_date(self) -> None:
        shipment = _make_in_transit_shipment()
        uc = DeliverShipment(FakeUoW(), FakeShipmentRepo([shipment]), FakeDispatcher())
        received = date(2026, 4, 20)

        result = await uc(
            DeliverShipmentCommand(
                workspace_id=WS, shipment_id=shipment.id, received_date=received
            ),
            _auth(),
        )

        assert result.unwrap().received_date == received

    async def test_deliver_not_found(self) -> None:
        uc = DeliverShipment(FakeUoW(), FakeShipmentRepo(), FakeDispatcher())

        result = await uc(
            DeliverShipmentCommand(workspace_id=WS, shipment_id=uuid.uuid4()), _auth()
        )

        assert isinstance(result, Failure)
        assert isinstance(result.failure(), NotFoundError)


class TestReturnShipment:
    async def test_returns_in_transit_shipment(self) -> None:
        shipment = _make_in_transit_shipment()
        uc = ReturnShipment(FakeUoW(), FakeShipmentRepo([shipment]), FakeDispatcher())

        result = await uc(ReturnShipmentCommand(workspace_id=WS, shipment_id=shipment.id), _auth())

        assert result.unwrap().status == ShipmentStatus.RETURNED

    async def test_return_not_found(self) -> None:
        uc = ReturnShipment(FakeUoW(), FakeShipmentRepo(), FakeDispatcher())

        result = await uc(
            ReturnShipmentCommand(workspace_id=WS, shipment_id=uuid.uuid4()), _auth()
        )

        assert isinstance(result, Failure)
        assert isinstance(result.failure(), NotFoundError)


# ---------------------------------------------------------------------------
# AddShipmentItem tests
# ---------------------------------------------------------------------------


class TestAddShipmentItem:
    async def test_adds_sample_item_to_preparing_shipment(self) -> None:
        shipment = _make_shipment()
        initial_count = len(shipment.items)
        sample = _sample()
        uc = _add_uc(FakeShipmentRepo([shipment]), samples=[sample])

        result = await uc(
            AddShipmentItemCommand(
                workspace_id=WS, shipment_id=shipment.id, item=_sample_input(sample, 3.0, "mg")
            ),
            _auth(),
        )

        updated = result.unwrap()
        assert len(updated.items) == initial_count + 1
        new_items = [i for i in updated.items if i.item_id == sample.id]
        assert len(new_items) == 1
        assert new_items[0].item_type == ShipmentItemType.SAMPLE
        assert new_items[0].amount_shipped.value == 3.0
        assert new_items[0].shipment_id == shipment.id

    async def test_adds_plate_item_without_amount(self) -> None:
        shipment = _make_shipment()
        plate = _plate(ORG_A)
        uc = _add_uc(FakeShipmentRepo([shipment]), plates=[plate])

        result = await uc(
            AddShipmentItemCommand(
                workspace_id=WS, shipment_id=shipment.id, item=_plate_input(plate)
            ),
            _auth(),
        )

        added = [i for i in result.unwrap().items if i.item_id == plate.id]
        assert len(added) == 1
        assert added[0].item_type == ShipmentItemType.PLATE
        assert added[0].amount_shipped is None

    async def test_add_hidden_plate_is_not_found(self) -> None:
        shipment = _make_shipment()
        plate = _plate(ORG_B)
        uc = _add_uc(FakeShipmentRepo([shipment]), plates=[plate])

        result = await uc(
            AddShipmentItemCommand(
                workspace_id=WS, shipment_id=shipment.id, item=_plate_input(plate)
            ),
            _auth(org_id=ORG_A),
        )

        assert isinstance(result, Failure)
        assert isinstance(result.failure(), NotFoundError)

    async def test_add_item_not_found(self) -> None:
        sample = _sample()
        uc = _add_uc(FakeShipmentRepo(), samples=[sample])

        result = await uc(
            AddShipmentItemCommand(
                workspace_id=WS, shipment_id=uuid.uuid4(), item=_sample_input(sample)
            ),
            _auth(),
        )

        assert isinstance(result, Failure)
        assert isinstance(result.failure(), NotFoundError)

    async def test_add_item_to_shipped_shipment_raises_domain_error(self) -> None:
        shipment = _make_shipped_shipment()
        sample = _sample()
        uc = _add_uc(FakeShipmentRepo([shipment]), samples=[sample])

        # Domain raises ValidationError on add_item — the use case doesn't
        # catch it, so it propagates as an exception
        with pytest.raises(ValidationError):
            await uc(
                AddShipmentItemCommand(
                    workspace_id=WS, shipment_id=shipment.id, item=_sample_input(sample)
                ),
                _auth(),
            )


# ---------------------------------------------------------------------------
# UpdateShipment tests — loan link
# ---------------------------------------------------------------------------


class TestUpdateShipmentLoan:
    async def test_sets_and_clears_loan(self) -> None:
        shipment = _make_shipment()
        loan = _loan(ORG_A, ORG_B)
        uc = _update_uc(FakeShipmentRepo([shipment]), loans=[loan])

        result = await uc(
            UpdateShipmentCommand(workspace_id=WS, shipment_id=shipment.id, loan_id=loan.id),
            _auth(),
        )
        assert result.unwrap().loan_id == loan.id

        result = await uc(
            UpdateShipmentCommand(workspace_id=WS, shipment_id=shipment.id, carrier="UPS"),
            _auth(),
        )
        assert result.unwrap().loan_id == loan.id  # UNSET leaves it alone

        result = await uc(
            UpdateShipmentCommand(workspace_id=WS, shipment_id=shipment.id, loan_id=None),
            _auth(),
        )
        assert result.unwrap().loan_id is None

    async def test_unknown_loan_is_not_found(self) -> None:
        shipment = _make_shipment()
        uc = _update_uc(FakeShipmentRepo([shipment]))

        result = await uc(
            UpdateShipmentCommand(workspace_id=WS, shipment_id=shipment.id, loan_id=uuid.uuid4()),
            _auth(),
        )

        assert isinstance(result, Failure)
        assert isinstance(result.failure(), NotFoundError)

    async def test_hidden_loan_is_not_found(self) -> None:
        shipment = _make_shipment()
        loan = _loan(ORG_B, ORG_B)
        uc = _update_uc(FakeShipmentRepo([shipment]), loans=[loan])

        result = await uc(
            UpdateShipmentCommand(workspace_id=WS, shipment_id=shipment.id, loan_id=loan.id),
            _auth(org_id=ORG_A),
        )

        assert isinstance(result, Failure)
        assert isinstance(result.failure(), NotFoundError)
