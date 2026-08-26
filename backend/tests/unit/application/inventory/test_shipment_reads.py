"""Unit tests for the shipment read side — resolve-items, item → shipments, loan → shipments."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace

from returns.result import Failure, Success

from cellar.application.inventory.plate_visibility import PlateVisibilityService
from cellar.application.inventory.shipment_reads import (
    ItemLabel,
    ListShipmentsForItem,
    ListShipmentsForItemQuery,
    ListShipmentsForLoan,
    ListShipmentsForLoanQuery,
    ResolvedItem,
    ResolveShipmentItems,
    ResolveShipmentItemsQuery,
    ShipmentLink,
    UnresolvedItem,
)
from cellar.domain.inventory.enums import PlateType, ShipmentItemType
from cellar.domain.inventory.registered_plate import RegisteredPlate
from cellar.domain.shared.enums import PlateFormat
from cellar.domain.shared.errors import NotFoundError
from cellar.domain.shared.value_objects import Barcode
from tests.fakes.fake_auth import FakeAuth
from tests.fakes.fake_registered_plate_repository import FakeRegisteredPlateRepository

WS = uuid.uuid4()
ORG_A = uuid.uuid4()
ORG_B = uuid.uuid4()


class _FakeUow:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class _FakeOrgDirectory:
    async def list_orgs(self):
        return [SimpleNamespace(id=ORG_A), SimpleNamespace(id=ORG_B)]


class _FakeSampleRepo:
    def __init__(self, samples=()) -> None:
        self._store = {s.id: s for s in samples}

    async def find_by_id_in_workspace(self, workspace_id, id):
        s = self._store.get(id)
        return s if s is not None and s.workspace_id == workspace_id else None

    async def find_by_barcode(self, workspace_id, barcode):
        return next(
            (
                s
                for s in self._store.values()
                if s.workspace_id == workspace_id and s.barcode.value == barcode
            ),
            None,
        )


class _FakeLoanRepo:
    def __init__(self, loans=(), borrowed=None) -> None:
        self._store = {loan.id: loan for loan in loans}
        self._borrowed = borrowed or set()

    async def find_by_id_in_workspace(self, workspace_id, id):
        loan = self._store.get(id)
        return loan if loan is not None and loan.workspace_id == workspace_id else None

    async def borrowed_plate_ids(self, workspace_id, org_id):
        return self._borrowed


class _StubReader:
    def __init__(self, rows=(), labels=None) -> None:
        self.rows = list(rows)
        self.labels = labels or {}
        self.calls: list[tuple] = []

    async def shipments_for_item(self, workspace_id, item_type, item_id):
        self.calls.append(("item", item_type, item_id))
        return self.rows

    async def shipments_for_loan(self, workspace_id, loan_id):
        self.calls.append(("loan", loan_id))
        return self.rows

    async def item_labels(self, workspace_id, plate_ids, sample_ids):
        self.calls.append(("labels", list(plate_ids), list(sample_ids)))
        wanted = set(plate_ids) | set(sample_ids)
        return {k: v for k, v in self.labels.items() if k[1] in wanted}


def _plate(owner_org_id, barcode=None) -> RegisteredPlate:
    return RegisteredPlate.register(
        workspace_id=WS,
        owner_org_id=owner_org_id,
        barcode=Barcode(value=barcode or f"PLT-{uuid.uuid4().hex[:8]}"),
        plate_label="Plate 1",
        format=PlateFormat.F96,
        plate_type=PlateType.ASSAY,
        registered_by=uuid.uuid4(),
    )


def _sample(barcode="S-1", ws=WS):
    return SimpleNamespace(
        id=uuid.uuid4(), workspace_id=ws, batch_id=uuid.uuid4(), barcode=Barcode(value=barcode)
    )


def _loan(owner, borrower):
    return SimpleNamespace(
        id=uuid.uuid4(), workspace_id=WS, owner_org_id=owner, borrower_org_id=borrower
    )


def _row() -> ShipmentLink:
    return ShipmentLink(
        shipment_id=uuid.uuid4(),
        direction="outbound",
        status="preparing",
        destination_org_id=uuid.uuid4(),
        tracking_number=None,
        carrier=None,
        shipping_date=None,
        received_date=None,
        amount_value=None,
        amount_unit=None,
        created_at=datetime.now(UTC),
    )


def _auth(role="editor", org_id=ORG_A, ws=WS):
    return FakeAuth(role=role, workspace_id=ws, org_id=org_id)


def _visibility(loan_repo=None):
    return PlateVisibilityService(_FakeOrgDirectory(), loan_repo)


# ---------------------------------------------------------------------------
# ResolveShipmentItems
# ---------------------------------------------------------------------------


class TestResolveShipmentItems:
    def _uc(self, *, plates=(), samples=(), reader=None, borrowed=None):
        return ResolveShipmentItems(
            _FakeUow(),
            FakeRegisteredPlateRepository(list(plates)),
            _FakeSampleRepo(samples),
            _visibility(_FakeLoanRepo(borrowed=borrowed)),
            reader or _StubReader(),
        )

    async def test_resolves_plate_sample_and_unknown(self) -> None:
        plate = _plate(ORG_A, barcode="005261")
        sample = _sample("VIAL-9")
        reader = _StubReader(
            labels={
                (ShipmentItemType.PLATE, plate.id): ItemLabel("005261", "Plate 1"),
                (ShipmentItemType.SAMPLE, sample.id): ItemLabel("VIAL-9", "B-0001"),
            }
        )
        uc = self._uc(plates=[plate], samples=[sample], reader=reader)

        result = await uc(
            ResolveShipmentItemsQuery(workspace_id=WS, barcodes=["5261", "VIAL-9", "", "nope"]),
            _auth(),
        )

        assert isinstance(result, Success)
        assert result.unwrap() == [
            ResolvedItem("5261", ShipmentItemType.PLATE, plate.id, "Plate 1"),
            ResolvedItem("VIAL-9", ShipmentItemType.SAMPLE, sample.id, "B-0001"),
            UnresolvedItem("nope", "Unknown barcode 'nope'"),
        ]
        assert reader.calls == [("labels", [plate.id], [sample.id])]

    async def test_hidden_plate_reads_as_unknown(self) -> None:
        plate = _plate(ORG_B, barcode="PLT-HIDDEN")
        uc = self._uc(plates=[plate])

        result = await uc(
            ResolveShipmentItemsQuery(workspace_id=WS, barcodes=["PLT-HIDDEN"]),
            _auth(org_id=ORG_A),
        )

        assert result.unwrap() == [UnresolvedItem("PLT-HIDDEN", "Unknown barcode 'PLT-HIDDEN'")]

    async def test_borrowed_plate_resolves(self) -> None:
        plate = _plate(ORG_B, barcode="PLT-LOANED")
        reader = _StubReader(
            labels={(ShipmentItemType.PLATE, plate.id): ItemLabel("PLT-LOANED", "Plate 1")}
        )
        uc = self._uc(plates=[plate], reader=reader, borrowed={plate.id})

        result = await uc(
            ResolveShipmentItemsQuery(workspace_id=WS, barcodes=["PLT-LOANED"]),
            _auth(org_id=ORG_A),
        )

        assert result.unwrap()[0].item_id == plate.id


# ---------------------------------------------------------------------------
# ListShipmentsForItem
# ---------------------------------------------------------------------------


class TestListShipmentsForItem:
    def _uc(self, *, plates=(), samples=(), reader, borrowed=None):
        return ListShipmentsForItem(
            _FakeUow(),
            FakeRegisteredPlateRepository(list(plates)),
            _FakeSampleRepo(samples),
            _visibility(_FakeLoanRepo(borrowed=borrowed)),
            reader,
        )

    async def test_visible_plate_returns_rows(self) -> None:
        plate = _plate(ORG_A)
        reader = _StubReader([_row()])

        result = await self._uc(plates=[plate], reader=reader)(
            ListShipmentsForItemQuery(
                workspace_id=WS, item_type=ShipmentItemType.PLATE, item_id=plate.id
            ),
            _auth(role="viewer"),
        )

        assert result.unwrap() == reader.rows
        assert reader.calls == [("item", ShipmentItemType.PLATE, plate.id)]

    async def test_hidden_plate_is_not_found(self) -> None:
        plate = _plate(ORG_B)
        reader = _StubReader([_row()])

        result = await self._uc(plates=[plate], reader=reader)(
            ListShipmentsForItemQuery(
                workspace_id=WS, item_type=ShipmentItemType.PLATE, item_id=plate.id
            ),
            _auth(org_id=ORG_A),
        )

        assert isinstance(result, Failure)
        assert isinstance(result.failure(), NotFoundError)
        assert reader.calls == []

    async def test_borrowed_plate_is_visible(self) -> None:
        plate = _plate(ORG_B)
        reader = _StubReader([_row()])

        result = await self._uc(plates=[plate], reader=reader, borrowed={plate.id})(
            ListShipmentsForItemQuery(
                workspace_id=WS, item_type=ShipmentItemType.PLATE, item_id=plate.id
            ),
            _auth(org_id=ORG_A),
        )

        assert isinstance(result, Success)

    async def test_sample_rows_and_missing_sample(self) -> None:
        sample = _sample()
        reader = _StubReader([_row()])
        uc = self._uc(samples=[sample], reader=reader)

        ok = await uc(
            ListShipmentsForItemQuery(
                workspace_id=WS, item_type=ShipmentItemType.SAMPLE, item_id=sample.id
            ),
            _auth(role="viewer"),
        )
        assert ok.unwrap() == reader.rows

        missing = await uc(
            ListShipmentsForItemQuery(
                workspace_id=WS, item_type=ShipmentItemType.SAMPLE, item_id=uuid.uuid4()
            ),
            _auth(role="viewer"),
        )
        assert isinstance(missing, Failure)
        assert isinstance(missing.failure(), NotFoundError)


# ---------------------------------------------------------------------------
# ListShipmentsForLoan
# ---------------------------------------------------------------------------


class TestListShipmentsForLoan:
    def _uc(self, loans, reader):
        loan_repo = _FakeLoanRepo(loans)
        return ListShipmentsForLoan(_FakeUow(), loan_repo, _visibility(loan_repo), reader)

    async def test_visible_loan_returns_rows(self) -> None:
        loan = _loan(ORG_A, ORG_B)
        reader = _StubReader([_row()])

        result = await self._uc([loan], reader)(
            ListShipmentsForLoanQuery(workspace_id=WS, loan_id=loan.id), _auth(role="viewer")
        )

        assert result.unwrap() == reader.rows
        assert reader.calls == [("loan", loan.id)]

    async def test_borrower_sees_private_owner_loan(self) -> None:
        loan = _loan(ORG_B, ORG_A)
        reader = _StubReader([_row()])

        result = await self._uc([loan], reader)(
            ListShipmentsForLoanQuery(workspace_id=WS, loan_id=loan.id), _auth(org_id=ORG_A)
        )

        assert isinstance(result, Success)

    async def test_hidden_and_missing_loans_are_not_found(self) -> None:
        loan = _loan(ORG_B, ORG_B)
        reader = _StubReader([_row()])
        uc = self._uc([loan], reader)

        hidden = await uc(
            ListShipmentsForLoanQuery(workspace_id=WS, loan_id=loan.id), _auth(org_id=ORG_A)
        )
        assert isinstance(hidden, Failure)
        assert isinstance(hidden.failure(), NotFoundError)

        missing = await uc(
            ListShipmentsForLoanQuery(workspace_id=WS, loan_id=uuid.uuid4()), _auth()
        )
        assert isinstance(missing, Failure)
        assert isinstance(missing.failure(), NotFoundError)
        assert reader.calls == []
