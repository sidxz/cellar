"""PlateLoan aggregate — the borrow/checkout workflow for registered plates.

Custody is DERIVED from the active loan item — never duplicated into
PlateStatus (which remains the physical lifecycle). One active item per plate
is pre-checked in the use case and backstopped by a partial unique index.
Policy collapse (skip approval / auto-confirm) is decided by the use case
from the owner org's OrgPlatePolicy; the aggregate exposes the raw verbs.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime

from cellar.domain.inventory.enums import (
    ACTIVE_LOAN_ITEM_STATUSES,
    VALID_LOAN_ITEM_TRANSITIONS,
    LoanItemStatus,
    LoanStatus,
)
from cellar.domain.inventory.events import (
    PlateLoanClosed,
    PlateLoanItemsApproved,
    PlateLoanItemsCancelled,
    PlateLoanItemsCheckedOut,
    PlateLoanItemsDenied,
    PlateLoanItemsReturned,
    PlateLoanItemsReturnRequested,
    PlateLoanRequested,
)
from cellar.domain.shared.entity import AggregateRoot, Entity
from cellar.domain.shared.errors import ValidationError

_TERMINAL = frozenset(
    {LoanItemStatus.RETURNED, LoanItemStatus.DENIED, LoanItemStatus.CANCELLED}
)


class LoanItem(Entity):
    """One plate's membership in a loan."""

    def __init__(
        self,
        *,
        id: uuid.UUID | None = None,
        loan_id: uuid.UUID,
        plate_id: uuid.UUID,
        status: LoanItemStatus = LoanItemStatus.REQUESTED,
        status_changed_at: datetime | None = None,
        created_at: datetime | None = None,
        updated_at: datetime | None = None,
    ) -> None:
        super().__init__(id=id, created_at=created_at, updated_at=updated_at)
        self.loan_id = loan_id
        self.plate_id = plate_id
        self.status = status
        self.status_changed_at = status_changed_at or datetime.now(UTC)


class PlateLoan(AggregateRoot):
    """A borrow request for one or more plates of a single owner org."""

    def __init__(
        self,
        *,
        id: uuid.UUID | None = None,
        workspace_id: uuid.UUID,
        owner_org_id: uuid.UUID,
        borrower_org_id: uuid.UUID,
        requested_by: uuid.UUID,
        approved_by: uuid.UUID | None = None,
        due_date: date | None = None,
        notes: str | None = None,
        status: LoanStatus = LoanStatus.OPEN,
        closed_at: datetime | None = None,
        items: list[LoanItem] | None = None,
        created_at: datetime | None = None,
        updated_at: datetime | None = None,
        version: int = 1,
    ) -> None:
        super().__init__(id=id, created_at=created_at, updated_at=updated_at, version=version)
        self.workspace_id = workspace_id
        self.owner_org_id = owner_org_id
        self.borrower_org_id = borrower_org_id
        self.requested_by = requested_by
        self.approved_by = approved_by
        self.due_date = due_date
        self.notes = notes
        self.status = status
        self.closed_at = closed_at
        self._items: list[LoanItem] = list(items or [])

    @property
    def items(self) -> list[LoanItem]:
        return list(self._items)

    @classmethod
    def request(
        cls,
        *,
        workspace_id: uuid.UUID,
        owner_org_id: uuid.UUID,
        borrower_org_id: uuid.UUID,
        requested_by: uuid.UUID,
        plate_ids: list[uuid.UUID],
        auto_approved: bool,
        due_date: date | None = None,
        notes: str | None = None,
    ) -> PlateLoan:
        if not plate_ids:
            raise ValidationError("A loan must include at least one plate")
        if len(set(plate_ids)) != len(plate_ids):
            raise ValidationError("Duplicate plates in loan request")
        loan = cls(
            workspace_id=workspace_id,
            owner_org_id=owner_org_id,
            borrower_org_id=borrower_org_id,
            requested_by=requested_by,
            due_date=due_date,
            notes=notes,
        )
        initial = LoanItemStatus.APPROVED if auto_approved else LoanItemStatus.REQUESTED
        loan._items = [
            LoanItem(loan_id=loan.id, plate_id=pid, status=initial) for pid in plate_ids
        ]
        loan.register_event(
            PlateLoanRequested(
                aggregate_id=loan.id,
                aggregate_type="PlateLoan",
                workspace_id=workspace_id,
                owner_org_id=owner_org_id,
                borrower_org_id=borrower_org_id,
                plate_ids=list(plate_ids),
                requested_by=requested_by,
            )
        )
        return loan

    # -- item verbs -----------------------------------------------------

    def approve_items(self, item_ids: list[uuid.UUID], *, approved_by: uuid.UUID) -> list[LoanItem]:
        items = self._transition(item_ids, LoanItemStatus.APPROVED)
        if self.approved_by is None:
            self.approved_by = approved_by
        self._emit(PlateLoanItemsApproved, item_ids=[i.id for i in items], approved_by=approved_by)
        self._refresh_status()
        return items

    def deny_items(self, item_ids: list[uuid.UUID]) -> list[LoanItem]:
        items = self._transition(item_ids, LoanItemStatus.DENIED)
        self._emit(PlateLoanItemsDenied, item_ids=[i.id for i in items])
        self._refresh_status()
        return items

    def confirm_checkout(self, item_ids: list[uuid.UUID]) -> list[LoanItem]:
        items = self._transition(item_ids, LoanItemStatus.CHECKED_OUT)
        self._emit(PlateLoanItemsCheckedOut, item_ids=[i.id for i in items])
        self._refresh_status()
        return items

    def request_return(self, item_ids: list[uuid.UUID]) -> list[LoanItem]:
        items = self._transition(item_ids, LoanItemStatus.RETURN_PENDING)
        self._emit(PlateLoanItemsReturnRequested, item_ids=[i.id for i in items])
        self._refresh_status()
        return items

    def confirm_return(self, item_ids: list[uuid.UUID]) -> list[LoanItem]:
        items = self._transition(item_ids, LoanItemStatus.RETURNED)
        self._emit(PlateLoanItemsReturned, item_ids=[i.id for i in items])
        self._refresh_status()
        return items

    def cancel_items(self, item_ids: list[uuid.UUID]) -> list[LoanItem]:
        items = self._transition(item_ids, LoanItemStatus.CANCELLED)
        self._emit(PlateLoanItemsCancelled, item_ids=[i.id for i in items])
        self._refresh_status()
        return items

    def eligible_item_ids(self, target: LoanItemStatus) -> list[uuid.UUID]:
        """Item ids currently in a valid source status for *target* — the
        routes' 'no item_ids given = act on all eligible' expansion."""
        sources = VALID_LOAN_ITEM_TRANSITIONS.get(target, frozenset())
        return [i.id for i in self._items if i.status in sources]

    # -- internals ------------------------------------------------------

    def _transition(
        self, item_ids: list[uuid.UUID], target: LoanItemStatus
    ) -> list[LoanItem]:
        if not item_ids:
            raise ValidationError("No loan items given")
        by_id = {i.id: i for i in self._items}
        sources = VALID_LOAN_ITEM_TRANSITIONS[target]
        items: list[LoanItem] = []
        for item_id in item_ids:
            item = by_id.get(item_id)
            if item is None:
                raise ValidationError(f"Loan item {item_id} is not part of this loan")
            if item.status not in sources:
                raise ValidationError(
                    f"Cannot move item from '{item.status.value}' to '{target.value}'"
                )
            items.append(item)
        now = datetime.now(UTC)
        for item in items:
            item.status = target
            item.status_changed_at = now
            item.updated_at = now
        self.updated_at = now
        return items

    def _emit(self, event_cls, **fields) -> None:
        self.register_event(
            event_cls(
                aggregate_id=self.id,
                aggregate_type="PlateLoan",
                workspace_id=self.workspace_id,
                **fields,
            )
        )

    def _refresh_status(self) -> None:
        if self.status == LoanStatus.OPEN and all(
            i.status in _TERMINAL for i in self._items
        ):
            self.status = LoanStatus.CLOSED
            self.closed_at = datetime.now(UTC)
            self._emit(PlateLoanClosed)
