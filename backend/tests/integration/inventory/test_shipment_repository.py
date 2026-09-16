"""Integration tests for SQLAlchemyShipmentRepository (S17: mixed items, direction, loan link)."""

from __future__ import annotations

import uuid

import pytest
import sqlalchemy as sa

from cellar.domain.inventory.enums import ShipmentDirection, ShipmentItemType, ShipmentStatus
from cellar.domain.inventory.plate_loan import PlateLoan
from cellar.domain.inventory.shipment import Shipment, ShipmentItem
from cellar.domain.shared.enums import AmountUnit
from cellar.domain.shared.value_objects import Amount
from cellar.infrastructure.persistence.sqlalchemy.inventory.plate_loan_repository import (
    SQLAlchemyPlateLoanRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.inventory.shipment_repository import (
    SQLAlchemyShipmentRepository,
)
from cellar.infrastructure.persistence.unit_of_work import AsyncUnitOfWork


async def _seed_loan(session_factory, ws: uuid.UUID) -> PlateLoan:
    loan = PlateLoan.request(
        workspace_id=ws,
        owner_org_id=uuid.uuid4(),
        borrower_org_id=uuid.uuid4(),
        requested_by=uuid.uuid4(),
        plate_ids=[uuid.uuid4()],
        auto_approved=True,
    )
    async with AsyncUnitOfWork(session_factory) as uow:
        await SQLAlchemyPlateLoanRepository(uow).save(loan)
        await uow.commit()
    return loan


@pytest.mark.integration
async def test_round_trip_mixed_inbound_shipment_with_loan(session_factory) -> None:
    ws = uuid.uuid4()
    loan = await _seed_loan(session_factory, ws)
    plate_id, sample_id = uuid.uuid4(), uuid.uuid4()
    shipment = Shipment.create(
        workspace_id=ws,
        destination_org_id=uuid.uuid4(),
        sender_id=uuid.uuid4(),
        direction=ShipmentDirection.INBOUND,
        loan_id=loan.id,
        items=[
            ShipmentItem(
                shipment_id=uuid.uuid4(), item_type=ShipmentItemType.PLATE, item_id=plate_id
            ),
            ShipmentItem(
                shipment_id=uuid.uuid4(),
                item_type=ShipmentItemType.SAMPLE,
                item_id=sample_id,
                amount_shipped=Amount(value=2.5, unit=AmountUnit.MG),
            ),
        ],
    )
    async with AsyncUnitOfWork(session_factory) as uow:
        await SQLAlchemyShipmentRepository(uow).save(shipment)
        await uow.commit()

    async with AsyncUnitOfWork(session_factory) as uow:
        repo = SQLAlchemyShipmentRepository(uow)
        loaded = await repo.find_by_id_in_workspace(ws, shipment.id)
        assert loaded is not None
        assert loaded.direction == ShipmentDirection.INBOUND
        assert loaded.loan_id == loan.id
        assert loaded.status == ShipmentStatus.PREPARING
        by_id = {i.item_id: i for i in loaded.items}
        assert by_id[plate_id].item_type == ShipmentItemType.PLATE
        assert by_id[plate_id].amount_shipped is None
        assert by_id[sample_id].item_type == ShipmentItemType.SAMPLE
        assert by_id[sample_id].amount_shipped == Amount(value=2.5, unit=AmountUnit.MG)

        loaded.update_details(loan_id=None)
        await repo.save(loaded)
        await uow.commit()

    async with AsyncUnitOfWork(session_factory) as uow:
        reloaded = await SQLAlchemyShipmentRepository(uow).find_by_id_in_workspace(ws, shipment.id)
        assert reloaded is not None
        assert reloaded.loan_id is None
        assert reloaded.version == 2


@pytest.mark.integration
async def test_row_inserted_without_direction_reads_back_outbound(session_factory) -> None:
    ws, sid = uuid.uuid4(), uuid.uuid4()
    async with AsyncUnitOfWork(session_factory) as uow:
        await uow.session.execute(
            sa.text(
                "INSERT INTO shipments "
                "(id, workspace_id, destination_org_id, sender_id, status, version) "
                "VALUES (:id, :ws, :org, :sender, 'preparing', 1)"
            ),
            {"id": sid, "ws": ws, "org": uuid.uuid4(), "sender": uuid.uuid4()},
        )
        await uow.commit()

    async with AsyncUnitOfWork(session_factory) as uow:
        loaded = await SQLAlchemyShipmentRepository(uow).find_by_id_in_workspace(ws, sid)
        assert loaded is not None
        assert loaded.direction == ShipmentDirection.OUTBOUND
        assert loaded.loan_id is None
        assert loaded.items == []
