"""Integration tests for SQLAlchemyPlateLoanRepository."""

from __future__ import annotations

import uuid
from datetime import date, timedelta

import pytest
from sqlalchemy.exc import IntegrityError

from cellar.application.inventory.plate_loans import (
    ApproveLoanItems,
    LoanItemsCommand,
    LoanWithPlates,
)
from cellar.application.inventory.plate_visibility import PlateVisibilityService
from cellar.domain.inventory.enums import LoanItemStatus, LoanStatus
from cellar.domain.inventory.plate_loan import PlateLoan
from cellar.infrastructure.persistence.sqlalchemy.inventory.org_plate_policy_repository import (
    SQLAlchemyOrgPlatePolicyRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.inventory.plate_loan_repository import (
    SQLAlchemyPlateLoanRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.inventory.registered_plate_repository import (
    SQLAlchemyRegisteredPlateRepository,
)
from cellar.infrastructure.persistence.unit_of_work import AsyncUnitOfWork
from tests.fakes.fake_auth import FakeAuth

OWNER_ORG = uuid.uuid4()
BORROWER_ORG = uuid.uuid4()
USER = uuid.uuid4()


def _request(
    ws: uuid.UUID,
    *,
    plate_ids: list[uuid.UUID],
    owner_org: uuid.UUID = OWNER_ORG,
    borrower_org: uuid.UUID = BORROWER_ORG,
    requested_by: uuid.UUID = USER,
    auto_approved: bool = True,
    due_date: date | None = None,
    notes: str | None = None,
) -> PlateLoan:
    return PlateLoan.request(
        workspace_id=ws,
        owner_org_id=owner_org,
        borrower_org_id=borrower_org,
        requested_by=requested_by,
        plate_ids=plate_ids,
        auto_approved=auto_approved,
        due_date=due_date,
        notes=notes,
    )


async def _save(session_factory, *loans: PlateLoan) -> None:
    async with AsyncUnitOfWork(session_factory) as uow:
        repo = SQLAlchemyPlateLoanRepository(uow)
        for loan in loans:
            await repo.save(loan)
        await uow.commit()


# ---------------------------------------------------------------------------
# (a) round trip with items + item statuses survive
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_round_trip_items_and_statuses(session_factory) -> None:
    ws = uuid.uuid4()
    p1, p2 = uuid.uuid4(), uuid.uuid4()
    loan = _request(
        ws, plate_ids=[p1, p2], auto_approved=False, due_date=date.today(), notes="urgent loan"
    )
    await _save(session_factory, loan)

    async with AsyncUnitOfWork(session_factory) as uow:
        repo = SQLAlchemyPlateLoanRepository(uow)
        loaded = await repo.find_by_id_in_workspace(ws, loan.id)
        assert loaded is not None
        assert loaded.owner_org_id == OWNER_ORG
        assert loaded.borrower_org_id == BORROWER_ORG
        assert loaded.requested_by == USER
        assert loaded.status == LoanStatus.OPEN
        assert loaded.due_date == date.today()
        assert loaded.notes == "urgent loan"
        assert loaded.version == 1
        assert {i.id for i in loaded.items} == {i.id for i in loan.items}
        assert {i.plate_id for i in loaded.items} == {p1, p2}
        assert all(i.status == LoanItemStatus.REQUESTED for i in loaded.items)


# ---------------------------------------------------------------------------
# (b) partial-unique violation; a CLOSED/RETURNED item does not block a new loan
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_partial_unique_index_blocks_second_active_loan_on_same_plate(
    session_factory,
) -> None:
    ws = uuid.uuid4()
    plate = uuid.uuid4()
    loan_a = _request(ws, plate_ids=[plate], auto_approved=True)
    await _save(session_factory, loan_a)

    loan_b = _request(ws, plate_ids=[plate], auto_approved=True)
    with pytest.raises(IntegrityError):
        await _save(session_factory, loan_b)


@pytest.mark.integration
async def test_returned_item_does_not_block_new_loan_on_same_plate(session_factory) -> None:
    ws = uuid.uuid4()
    plate = uuid.uuid4()
    loan_a = _request(ws, plate_ids=[plate], auto_approved=True)
    await _save(session_factory, loan_a)

    item_id = loan_a.items[0].id
    loan_a.confirm_checkout([item_id])
    loan_a.request_return([item_id])
    loan_a.confirm_return([item_id])
    assert loan_a.status == LoanStatus.CLOSED
    await _save(session_factory, loan_a)

    # Same plate, new loan — must succeed now that the old item is terminal.
    loan_c = _request(ws, plate_ids=[plate], auto_approved=True)
    await _save(session_factory, loan_c)

    async with AsyncUnitOfWork(session_factory) as uow:
        repo = SQLAlchemyPlateLoanRepository(uow)
        reloaded_a = await repo.find_by_id_in_workspace(ws, loan_a.id)
        assert reloaded_a is not None
        assert reloaded_a.status == LoanStatus.CLOSED
        assert reloaded_a.items[0].status == LoanItemStatus.RETURNED
        reloaded_c = await repo.find_by_id_in_workspace(ws, loan_c.id)
        assert reloaded_c is not None
        assert reloaded_c.items[0].status == LoanItemStatus.APPROVED


# ---------------------------------------------------------------------------
# (c) active_plate_ids returns exactly the active subset
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_active_plate_ids_returns_active_subset(session_factory) -> None:
    ws = uuid.uuid4()
    active_plate = uuid.uuid4()
    returned_plate = uuid.uuid4()
    unrelated_plate = uuid.uuid4()

    loan = _request(ws, plate_ids=[active_plate, returned_plate], auto_approved=True)
    returned_item_id = next(i.id for i in loan.items if i.plate_id == returned_plate)
    await _save(session_factory, loan)

    loan.confirm_checkout([returned_item_id])
    loan.request_return([returned_item_id])
    loan.confirm_return([returned_item_id])
    await _save(session_factory, loan)

    async with AsyncUnitOfWork(session_factory) as uow:
        repo = SQLAlchemyPlateLoanRepository(uow)
        result = await repo.active_plate_ids(ws, [active_plate, returned_plate, unrelated_plate])
        assert result == {active_plate}


# ---------------------------------------------------------------------------
# (d) borrowed_plate_ids filters by borrower org and active status
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_borrowed_plate_ids_filters_by_borrower_and_active(session_factory) -> None:
    ws = uuid.uuid4()
    borrower_a = uuid.uuid4()
    borrower_b = uuid.uuid4()
    plate_a_active = uuid.uuid4()
    plate_a_returned = uuid.uuid4()
    plate_b_active = uuid.uuid4()

    loan_a = _request(
        ws,
        plate_ids=[plate_a_active, plate_a_returned],
        borrower_org=borrower_a,
        auto_approved=True,
    )
    loan_b = _request(ws, plate_ids=[plate_b_active], borrower_org=borrower_b, auto_approved=True)
    returned_item_id = next(i.id for i in loan_a.items if i.plate_id == plate_a_returned)
    await _save(session_factory, loan_a, loan_b)

    loan_a.confirm_checkout([returned_item_id])
    loan_a.request_return([returned_item_id])
    loan_a.confirm_return([returned_item_id])
    await _save(session_factory, loan_a)

    async with AsyncUnitOfWork(session_factory) as uow:
        repo = SQLAlchemyPlateLoanRepository(uow)
        result = await repo.borrowed_plate_ids(ws, borrower_a)
        assert result == {plate_a_active}


# ---------------------------------------------------------------------------
# (e) find_by_workspace(overdue=True): only OPEN loans with due_date < today
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_find_by_workspace_overdue_filters_open_and_past_due(session_factory) -> None:
    ws = uuid.uuid4()
    yesterday = date.today() - timedelta(days=1)
    tomorrow = date.today() + timedelta(days=1)

    overdue_loan = _request(ws, plate_ids=[uuid.uuid4()], due_date=yesterday, auto_approved=True)
    due_tomorrow_loan = _request(
        ws, plate_ids=[uuid.uuid4()], due_date=tomorrow, auto_approved=True
    )
    overdue_closed_loan = _request(
        ws, plate_ids=[uuid.uuid4()], due_date=yesterday, auto_approved=True
    )
    await _save(session_factory, overdue_loan, due_tomorrow_loan, overdue_closed_loan)

    # Cancel its only item — terminal status closes the loan even though overdue.
    overdue_closed_loan.cancel_items([overdue_closed_loan.items[0].id])
    assert overdue_closed_loan.status == LoanStatus.CLOSED
    await _save(session_factory, overdue_closed_loan)

    async with AsyncUnitOfWork(session_factory) as uow:
        repo = SQLAlchemyPlateLoanRepository(uow)
        results = await repo.find_by_workspace(ws, overdue=True)
        assert [r.id for r in results] == [overdue_loan.id]


# ---------------------------------------------------------------------------
# (f) find_by_workspace(plate_id=...) finds the loan through its item
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_find_by_workspace_plate_id_finds_loan_through_item(session_factory) -> None:
    ws = uuid.uuid4()
    plate = uuid.uuid4()
    other_plate = uuid.uuid4()
    loan = _request(ws, plate_ids=[plate], auto_approved=True)
    await _save(session_factory, loan)

    async with AsyncUnitOfWork(session_factory) as uow:
        repo = SQLAlchemyPlateLoanRepository(uow)
        found = await repo.find_by_workspace(ws, plate_id=plate)
        assert [f.id for f in found] == [loan.id]
        assert await repo.find_by_workspace(ws, plate_id=other_plate) == []


# ---------------------------------------------------------------------------
# (g) wholesale item update: status + status_changed_at persist, version +1
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_wholesale_item_update_persists_and_bumps_version_once(session_factory) -> None:
    ws = uuid.uuid4()
    plate = uuid.uuid4()
    loan = _request(ws, plate_ids=[plate], auto_approved=False)
    await _save(session_factory, loan)

    async with AsyncUnitOfWork(session_factory) as uow:
        repo = SQLAlchemyPlateLoanRepository(uow)
        loaded = await repo.find_by_id_in_workspace(ws, loan.id)
        assert loaded is not None
        assert loaded.version == 1
        item_id = loaded.items[0].id
        original_status_changed_at = loaded.items[0].status_changed_at

        loaded.approve_items([item_id], approved_by=USER)
        expected_status_changed_at = loaded.items[0].status_changed_at
        assert expected_status_changed_at != original_status_changed_at

        await repo.save(loaded)
        await uow.commit()
        assert loaded.version == 2

    async with AsyncUnitOfWork(session_factory) as uow:
        repo = SQLAlchemyPlateLoanRepository(uow)
        reloaded = await repo.find_by_id_in_workspace(ws, loan.id)
        assert reloaded is not None
        assert reloaded.version == 2
        assert reloaded.approved_by == USER
        ritem = reloaded.items[0]
        assert ritem.id == item_id
        assert ritem.status == LoanItemStatus.APPROVED
        assert ritem.status_changed_at == expected_status_changed_at


# ---------------------------------------------------------------------------
# (h) full ApproveLoanItems success path with real repos — proves enrichment
#     runs on a live session (regression: post-uow-block _enrich raised
#     RuntimeError after commit, turning every successful transition into a 500)
# ---------------------------------------------------------------------------


class _StubDispatcher:
    async def dispatch_all(self, events) -> None:
        pass


@pytest.mark.integration
async def test_approve_loan_items_success_path_enriches_inside_uow(session_factory) -> None:
    ws = uuid.uuid4()
    loan = _request(ws, plate_ids=[uuid.uuid4()], auto_approved=False)
    await _save(session_factory, loan)

    uow = AsyncUnitOfWork(session_factory)
    use_case = ApproveLoanItems(
        uow,
        SQLAlchemyPlateLoanRepository(uow),
        SQLAlchemyRegisteredPlateRepository(uow),
        SQLAlchemyOrgPlatePolicyRepository(uow),
        _StubDispatcher(),
        PlateVisibilityService(),
    )
    auth = FakeAuth(role="admin", workspace_id=ws)  # admin bypasses org + action checks

    result = await use_case(LoanItemsCommand(workspace_id=ws, loan_id=loan.id), auth=auth)

    enriched = result.unwrap()  # raises if the use case returned Failure
    assert isinstance(enriched, LoanWithPlates)
    # No policy row → default ADMIN_CONFIRM → no checkout collapse.
    assert [i.status for i in enriched.loan.items] == [LoanItemStatus.APPROVED]
    assert enriched.loan.approved_by == auth.user_id

    async with AsyncUnitOfWork(session_factory) as verify_uow:
        repo = SQLAlchemyPlateLoanRepository(verify_uow)
        persisted = await repo.find_by_id_in_workspace(ws, loan.id)
        assert persisted is not None
        assert persisted.items[0].status == LoanItemStatus.APPROVED
