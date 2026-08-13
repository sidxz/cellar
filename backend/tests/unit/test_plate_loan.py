"""Unit tests for the PlateLoan aggregate + item state machine."""

from __future__ import annotations

import uuid
from datetime import date

import pytest

from cellar.domain.inventory.enums import LoanItemStatus, LoanStatus
from cellar.domain.inventory.events import (
    PlateLoanClosed,
    PlateLoanItemsApproved,
    PlateLoanRequested,
)
from cellar.domain.inventory.plate_loan import PlateLoan
from cellar.domain.shared.errors import ValidationError

WS = uuid.uuid4()
OWNER = uuid.uuid4()
BORROWER = uuid.uuid4()
USER = uuid.uuid4()


def _loan(n_plates: int = 2, *, auto_approved: bool = False, **overrides) -> PlateLoan:
    kwargs = dict(
        workspace_id=WS,
        owner_org_id=OWNER,
        borrower_org_id=BORROWER,
        requested_by=USER,
        plate_ids=[uuid.uuid4() for _ in range(n_plates)],
        auto_approved=auto_approved,
        due_date=date(2026, 9, 1),
        notes=None,
    )
    kwargs.update(overrides)
    return PlateLoan.request(**kwargs)


class TestRequest:
    def test_request_creates_requested_items_and_event(self) -> None:
        loan = _loan(2)
        assert loan.status == LoanStatus.OPEN
        assert len(loan.items) == 2
        assert all(i.status == LoanItemStatus.REQUESTED for i in loan.items)
        assert all(i.loan_id == loan.id for i in loan.items)
        (event,) = loan.collect_events()
        assert isinstance(event, PlateLoanRequested)
        assert event.owner_org_id == OWNER
        assert event.borrower_org_id == BORROWER
        assert len(event.plate_ids) == 2

    def test_auto_approved_items_start_approved(self) -> None:
        loan = _loan(1, auto_approved=True)
        assert loan.items[0].status == LoanItemStatus.APPROVED

    def test_empty_plate_list_rejected(self) -> None:
        with pytest.raises(ValidationError):
            _loan(0)

    def test_duplicate_plate_ids_rejected(self) -> None:
        pid = uuid.uuid4()
        with pytest.raises(ValidationError):
            _loan(plate_ids=[pid, pid])


class TestTransitions:
    def test_full_happy_path_closes_loan(self) -> None:
        loan = _loan(1)
        item_id = loan.items[0].id
        loan.clear_events()
        loan.approve_items([item_id], approved_by=USER)
        assert loan.items[0].status == LoanItemStatus.APPROVED
        assert loan.approved_by == USER
        loan.confirm_checkout([item_id])
        loan.request_return([item_id])
        loan.confirm_return([item_id])
        assert loan.items[0].status == LoanItemStatus.RETURNED
        assert loan.status == LoanStatus.CLOSED
        assert loan.closed_at is not None
        events = loan.collect_events()
        assert isinstance(events[0], PlateLoanItemsApproved)
        assert isinstance(events[-1], PlateLoanClosed)

    def test_deny_and_cancel_close_when_all_terminal(self) -> None:
        loan = _loan(2)
        a, b = (i.id for i in loan.items)
        loan.deny_items([a])
        assert loan.status == LoanStatus.OPEN
        loan.cancel_items([b])
        assert loan.status == LoanStatus.CLOSED

    def test_invalid_source_status_rejected(self) -> None:
        loan = _loan(1)
        with pytest.raises(ValidationError):
            loan.confirm_checkout([loan.items[0].id])  # still REQUESTED

    def test_unknown_item_id_rejected(self) -> None:
        loan = _loan(1)
        with pytest.raises(ValidationError):
            loan.approve_items([uuid.uuid4()], approved_by=USER)

    def test_cancel_allowed_from_approved(self) -> None:
        loan = _loan(1, auto_approved=True)
        loan.cancel_items([loan.items[0].id])
        assert loan.items[0].status == LoanItemStatus.CANCELLED

    def test_eligible_item_ids_filters_by_source(self) -> None:
        loan = _loan(2)
        a, b = (i.id for i in loan.items)
        loan.approve_items([a], approved_by=USER)
        assert loan.eligible_item_ids(LoanItemStatus.APPROVED) == [b]
        assert loan.eligible_item_ids(LoanItemStatus.CHECKED_OUT) == [a]
