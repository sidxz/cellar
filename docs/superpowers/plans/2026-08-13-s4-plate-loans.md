# S4 — PlateLoan Workflow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The plate loan/checkout workflow — `PlateLoan` aggregate with a policy-driven item state machine, the repo's first runtime RBAC action check, loan APIs, borrowed-plate read visibility, and the FE loan flows + custody chips. Task 1 lands the user-decided plate↔group membership audit event.

**Architecture:** `PlateLoan` root + owned `LoanItem` entities (Shipment persistence pattern: two tables, wholesale child reassignment, root-only version). Item machine REQUESTED→APPROVED→CHECKED_OUT→RETURN_PENDING→RETURNED (+DENIED/CANCELLED), collapsed per the **owner org's** `OrgPlatePolicy`. One-active-item-per-plate enforced by a raw-SQL partial unique index (049 pattern). Approval authority = the first `check_action` call in the codebase (`cellar:approve_loan`) composed with owner-org membership; `is_admin` bypasses both. Custody is derived from active items — never duplicated into `PlateStatus`.

**Tech Stack:** unchanged from S3 (FastAPI/SQLAlchemy async/Alembic — next migration **063**; Next.js 16/TanStack v5; no new FE deps).

**Spec:** `docs/superpowers/specs/2026-08-10-inventory-plate-org-loans-spec.md` §4.3-§4.4, §5, §7, §8-§11, §14-S4.

## Global Constraints

- **Spec-sync deviations locked here (record in the spec file in Task 13):** (1) the approval action is **`cellar:approve_loan`** (house `cellar:<verb>` registry convention in `infrastructure/duar/auth.py::SERVICE_ACTIONS`), not the spec's `inventory.plate_loans.approve` notation; (2) item events are **batch-shaped** (`PlateLoanItemsApproved{item_ids}` etc.) matching the batch API verbs, not per-item; (3) borrowed-plate visibility (spec §5 "plate has an active loan with borrower_org_id == U.org") is wired into **read surfaces only** (GetPlate/ListPlates/ListChildren/molecule-plates read model) — borrowers can see, not modify; write/export/tag surfaces keep strict S2 privacy; (4) `is_admin` bypasses the action check too (not just the org check) — prevents the ungranted-action deadlock since no Sentinel grants exist yet.
- **Authority rule (owner-side verbs approve/deny/confirm-out/confirm-in):** `auth.is_admin` OR (`auth.org_id == loan.owner_org_id` AND `await auth.check_action("cellar:approve_loan")`). Borrower-side verbs (request-return, cancel): editor AND (`auth.org_id == loan.borrower_org_id` OR `auth.is_admin`).
- **Visibility:** loans hidden==missing 404 when `owner_org_id ∈ excluded` UNLESS `auth.org_id == borrower_org_id`. All plate resolution in RequestPlateLoan applies the S2 excluded set (hidden plate == missing plate; barcode misses and hidden plates report identically — no existence oracle).
- **Policy collapse (owner org's policy, get-or-default):** `require_approval=false` → items created APPROVED; `confirmation=none` → APPROVED auto-advances to CHECKED_OUT and RETURN_PENDING auto-advances to RETURNED, in the same command; `default_due_days` fills a missing `due_date` (None stays None). `kiosk_scan` behaves like `admin_confirm` until S5 (kiosk endpoints) — the confirm verbs work for authorized users either way.
- **One active item per plate:** application-level pre-check (409 listing the conflicting barcodes) + DB partial unique index `WHERE status IN ('requested','approved','checked_out','return_pending')` as the race backstop.
- **Custody is derived** — never write `PlateStatus` from loan code.
- **No UUIDs in UI** (barcodes/labels/org names); explicit gestures (no autosave); count badges next to actions, not inside them; CSV import has a Download Template button (client-side `saveText`).
- **Test commands:** backend `uv run pytest tests/unit -x -q` / `uv run pytest tests/api/test_plate_loans.py -q` (needs `make up`); FE `/Users/sidx/Library/pnpm/pnpm exec vitest run <paths>` / `exec tsc --noEmit` / `exec biome check <paths>` (bare `pnpm` and `make dev-fe` are broken on this machine — always use the full pnpm path). Backend baseline = 10 documented failures; FE baseline = 983 green.
- **Commits:** always `git commit -m "..." -- <explicit paths>`; never `frontend/package.json`/`pnpm-lock.yaml`/`next-env.d.ts` (user's unrelated Sentinel-bump edits still in the working tree).
- **Orval:** regenerate in the same change as any route/DTO change; alias generated types, never hand-roll mirrors.

---

### Task 1: PlateGroupMembershipChanged audit event (user decision 2026-08-13)

**Files:**
- Modify: `backend/src/cellar/domain/inventory/events.py`
- Modify: `backend/src/cellar/domain/inventory/registered_plate.py` (`assign_to_group` emits)
- Modify: `backend/src/cellar/domain/inventory/plate_group.py` (docstring: decision superseded)
- Test: `backend/tests/unit/test_registered_plate.py` (extend `TestGroupAssignment`)

**Interfaces:**
- Produces: `PlateGroupMembershipChanged{plate_id, old_group_id, new_group_id}` on `DomainEvent` — flows into the audit trail automatically (catch-all `dispatcher.register(DomainEvent, AuditEventHandler)` in `app.py`; no registration needed). `AssignPlatesToGroup`/`RemovePlatesFromGroup` already save plates through the repo and collect via `uow.commit()` — zero application changes.

- [ ] **Step 1: Failing test.** In `backend/tests/unit/test_registered_plate.py`, extend `TestGroupAssignment` (constructing plates exactly as the class's existing tests do):

```python
    def test_assign_to_group_emits_membership_event(self) -> None:
        plate = _make_plate()
        plate.clear_events()
        gid = uuid.uuid4()
        plate.assign_to_group(gid)
        events = plate.collect_events()
        assert len(events) == 1
        assert isinstance(events[0], PlateGroupMembershipChanged)
        assert events[0].plate_id == plate.id
        assert events[0].old_group_id is None
        assert events[0].new_group_id == gid
        plate.clear_events()
        plate.assign_to_group(None)
        (cleared,) = plate.collect_events()
        assert cleared.old_group_id == gid
        assert cleared.new_group_id is None
```

(Add the `PlateGroupMembershipChanged` import; reuse the file's plate factory/inline construction.) Run: `cd backend && uv run pytest tests/unit/test_registered_plate.py -q` — FAIL (ImportError).

- [ ] **Step 2: Implement.** In `events.py` (next to the PlateGroup events):

```python
@dataclass(frozen=True, kw_only=True)
class PlateGroupMembershipChanged(DomainEvent):
    """A plate was assigned to / removed from / moved between groups.

    User decision 2026-08-13: grouping IS audited — this was the one
    un-audited mutation class on a 21-CFR-tracked aggregate."""

    plate_id: uuid.UUID
    old_group_id: uuid.UUID | None
    new_group_id: uuid.UUID | None
```

In `registered_plate.py`, `assign_to_group` becomes:

```python
    def assign_to_group(self, group_id: uuid.UUID | None) -> None:
        """Set or clear this plate's group. The plate-org == group-org
        invariant is enforced by the use case, which holds both aggregates."""
        old = self.group_id
        self.group_id = group_id
        self.updated_at = datetime.now(UTC)
        self.register_event(
            PlateGroupMembershipChanged(
                aggregate_id=self.id,
                aggregate_type="RegisteredPlate",
                workspace_id=self.workspace_id,
                plate_id=self.id,
                old_group_id=old,
                new_group_id=group_id,
            )
        )
```

(Add the import.) In `plate_group.py`'s module docstring, replace the "grouping is manual curation, not lineage" bullet's context if it implies un-audited: append ` Membership changes emit ``PlateGroupMembershipChanged`` (audited — user decision 2026-08-13).` to that bullet.

- [ ] **Step 3: Run.** `cd backend && uv run pytest tests/unit/test_registered_plate.py tests/unit/test_plate_group.py tests/unit/test_plate_group_tree.py -q` — PASS. Also `uv run pytest tests/api/test_plate_groups.py -q` (assign/remove flows still green — events ride the existing commit path).

- [ ] **Step 4: Commit.**

```bash
git commit -m "feat(domain): audit plate<->group membership via PlateGroupMembershipChanged (user decision)" -- backend/src/cellar/domain/inventory/events.py backend/src/cellar/domain/inventory/registered_plate.py backend/src/cellar/domain/inventory/plate_group.py backend/tests/unit/test_registered_plate.py
```

---

### Task 2: PlateLoan domain — aggregate, item machine, events

**Files:**
- Modify: `backend/src/cellar/domain/inventory/enums.py` (`LoanStatus`, `LoanItemStatus`, `ACTIVE_LOAN_ITEM_STATUSES`, `VALID_LOAN_ITEM_TRANSITIONS`)
- Create: `backend/src/cellar/domain/inventory/plate_loan.py`
- Modify: `backend/src/cellar/domain/inventory/events.py` (loan events)
- Test: `backend/tests/unit/test_plate_loan.py` (new)

**Interfaces:**
- Consumes: `AggregateRoot`/`Entity`, `ValidationError`, `DomainEvent`.
- Produces (Tasks 3-6 rely on these exact names): `LoanStatus{OPEN,CLOSED}`, `LoanItemStatus{REQUESTED,APPROVED,CHECKED_OUT,RETURN_PENDING,RETURNED,DENIED,CANCELLED}`, `ACTIVE_LOAN_ITEM_STATUSES: frozenset[LoanItemStatus]` (requested/approved/checked_out/return_pending); `LoanItem(Entity){loan_id, plate_id, status, status_changed_at}`; `PlateLoan(AggregateRoot)` with `request(cls, *, workspace_id, owner_org_id, borrower_org_id, requested_by, plate_ids, auto_approved: bool, due_date, notes) -> PlateLoan`, item verbs `approve_items(item_ids, approved_by)` / `deny_items(item_ids)` / `confirm_checkout(item_ids)` / `request_return(item_ids)` / `confirm_return(item_ids)` / `cancel_items(item_ids)` — each returns the list of affected `LoanItem`s, validates eligibility, touches `status_changed_at`, emits its batch event, then closes the loan when every item is terminal; `items` property; `eligible_item_ids(target_status) -> list[uuid.UUID]` helper (used by routes' "None = all eligible"). Events: `PlateLoanRequested{owner_org_id, borrower_org_id, plate_ids, requested_by}`, `PlateLoanItemsApproved{item_ids, approved_by}`, `PlateLoanItemsDenied{item_ids}`, `PlateLoanItemsCheckedOut{item_ids}`, `PlateLoanItemsReturnRequested{item_ids}`, `PlateLoanItemsReturned{item_ids}`, `PlateLoanItemsCancelled{item_ids}`, `PlateLoanClosed{}` (base fields only).

**Machine (single source of truth in `enums.py`):**

```python
class LoanStatus(StrEnum):
    OPEN = "open"
    CLOSED = "closed"


class LoanItemStatus(StrEnum):
    REQUESTED = "requested"
    APPROVED = "approved"
    CHECKED_OUT = "checked_out"
    RETURN_PENDING = "return_pending"
    RETURNED = "returned"
    DENIED = "denied"
    CANCELLED = "cancelled"


ACTIVE_LOAN_ITEM_STATUSES: frozenset[LoanItemStatus] = frozenset(
    {
        LoanItemStatus.REQUESTED,
        LoanItemStatus.APPROVED,
        LoanItemStatus.CHECKED_OUT,
        LoanItemStatus.RETURN_PENDING,
    }
)

# target -> allowed sources (approve-all/deny-all etc. filter by these)
VALID_LOAN_ITEM_TRANSITIONS: dict[LoanItemStatus, frozenset[LoanItemStatus]] = {
    LoanItemStatus.APPROVED: frozenset({LoanItemStatus.REQUESTED}),
    LoanItemStatus.DENIED: frozenset({LoanItemStatus.REQUESTED}),
    LoanItemStatus.CHECKED_OUT: frozenset({LoanItemStatus.APPROVED}),
    LoanItemStatus.RETURN_PENDING: frozenset({LoanItemStatus.CHECKED_OUT}),
    LoanItemStatus.RETURNED: frozenset({LoanItemStatus.RETURN_PENDING}),
    LoanItemStatus.CANCELLED: frozenset(
        {LoanItemStatus.REQUESTED, LoanItemStatus.APPROVED}
    ),
}
```

- [ ] **Step 1: Failing unit tests** — `backend/tests/unit/test_plate_loan.py`:

```python
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
```

Run: `cd backend && uv run pytest tests/unit/test_plate_loan.py -q` — FAIL (imports missing).

- [ ] **Step 2: Implement.** Add the enums block above to `enums.py`. Add the eight event dataclasses to `events.py` (all `@dataclass(frozen=True, kw_only=True)` on `DomainEvent`; fields per the Produces block — `plate_ids: list[uuid.UUID]`, `item_ids: list[uuid.UUID]`, `approved_by: uuid.UUID` where named). Create `backend/src/cellar/domain/inventory/plate_loan.py` (Shipment idioms: `_items` list + defensive-copy property, `Entity` child):

```python
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
        # Dedupe preserving order — callers may union checked+eligible lists;
        # a duplicated id must not double-appear in events/returns.
        item_ids = list(dict.fromkeys(item_ids))
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
        # Terminality = complement of the SSOT active set (enums.py) — never
        # a hand-maintained second list.
        if self.status == LoanStatus.OPEN and all(
            i.status not in ACTIVE_LOAN_ITEM_STATUSES for i in self._items
        ):
            self.status = LoanStatus.CLOSED
            self.closed_at = datetime.now(UTC)
            self._emit(PlateLoanClosed)
```

- [ ] **Step 3: Run.** `cd backend && uv run pytest tests/unit/test_plate_loan.py tests/unit -q` — PASS, no regressions.

- [ ] **Step 4: Commit.**

```bash
git commit -m "feat(domain): PlateLoan aggregate + item state machine + events" -- backend/src/cellar/domain/inventory/enums.py backend/src/cellar/domain/inventory/plate_loan.py backend/src/cellar/domain/inventory/events.py backend/tests/unit/test_plate_loan.py
```

---

### Task 3: Persistence — migration 063, ORM, repository

**Files:**
- Create: `backend/alembic/versions/063_plate_loans.py`
- Create: `backend/src/cellar/infrastructure/persistence/sqlalchemy/inventory/plate_loan_models.py`
- Create: `backend/src/cellar/infrastructure/persistence/sqlalchemy/inventory/plate_loan_repository.py`
- Modify: `backend/src/cellar/domain/inventory/repository.py` (`PlateLoanRepository` protocol; `find_by_ids` on `RegisteredPlateRepository`)
- Modify: `backend/src/cellar/infrastructure/persistence/sqlalchemy/inventory/registered_plate_repository.py` (`find_by_ids`)
- Modify: `backend/tests/unit/cascade/test_fk_coverage.py` (categorize the two new FKs — follow Task-4-of-S3's precedent: `plate_loan_items.loan_id` CASCADE is Tier-membership-style; check the file's actual categories and place `plate_loans` parent/`plate_id` loose-ref per the existing `IGNORED_FKS`/tier conventions with justifying comments)
- Test: `backend/tests/integration/inventory/test_plate_loan_repository.py` (new)

**Interfaces:**
- Consumes: Task 2's domain.
- Produces: `PlateLoanRepository` protocol —

```python
@runtime_checkable
class PlateLoanRepository(Protocol):
    """Repository for PlateLoan aggregates (items loaded eagerly)."""

    async def find_by_id_in_workspace(
        self, workspace_id: uuid.UUID, id: uuid.UUID
    ) -> PlateLoan | None: ...
    async def find_by_workspace(
        self,
        workspace_id: uuid.UUID,
        *,
        status: str | None = None,
        owner_org_id: uuid.UUID | None = None,
        borrower_org_id: uuid.UUID | None = None,
        requested_by: uuid.UUID | None = None,
        plate_id: uuid.UUID | None = None,
        overdue: bool = False,
    ) -> list[PlateLoan]: ...
    async def active_plate_ids(
        self, workspace_id: uuid.UUID, plate_ids: list[uuid.UUID]
    ) -> set[uuid.UUID]: ...
    async def borrowed_plate_ids(
        self, workspace_id: uuid.UUID, borrower_org_id: uuid.UUID
    ) -> set[uuid.UUID]: ...
    async def save(self, aggregate: PlateLoan) -> None: ...
```

  plus `RegisteredPlateRepository.find_by_ids(workspace_id, ids: list[uuid.UUID]) -> list[RegisteredPlate]` (Batch has the same method — mirror it).

- [ ] **Step 1: Migration** `063_plate_loans.py` (`down_revision = "062_plate_groups"`; mirror 062's column idioms):

```python
def upgrade() -> None:
    op.create_table(
        "plate_loans",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("owner_org_id", sa.Uuid(), nullable=False),
        sa.Column("borrower_org_id", sa.Uuid(), nullable=False),
        sa.Column("requested_by", sa.Uuid(), nullable=False),
        sa.Column("approved_by", sa.Uuid(), nullable=True),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("status", sa.String(10), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_plate_loans_ws_status", "plate_loans", ["workspace_id", "status"])
    op.create_index("ix_plate_loans_owner_org", "plate_loans", ["owner_org_id"])
    op.create_index("ix_plate_loans_borrower_org", "plate_loans", ["borrower_org_id"])

    op.create_table(
        "plate_loan_items",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("loan_id", sa.Uuid(), nullable=False),
        sa.Column("plate_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("status_changed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["loan_id"], ["plate_loans.id"], name="fk_loan_items_loan", ondelete="CASCADE"
        ),
    )
    op.create_index("ix_loan_items_loan", "plate_loan_items", ["loan_id"])
    op.create_index("ix_loan_items_plate", "plate_loan_items", ["plate_id"])
    # Partial UNIQUE index — raw SQL (049/062 precedent; op.create_index can't
    # express unique+where reliably across this repo's conventions).
    op.execute(
        """
        CREATE UNIQUE INDEX uq_loan_items_active_plate ON plate_loan_items (plate_id)
            WHERE status IN ('requested', 'approved', 'checked_out', 'return_pending');
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_loan_items_active_plate")
    op.drop_index("ix_loan_items_plate", table_name="plate_loan_items")
    op.drop_index("ix_loan_items_loan", table_name="plate_loan_items")
    op.drop_table("plate_loan_items")
    op.drop_index("ix_plate_loans_borrower_org", table_name="plate_loans")
    op.drop_index("ix_plate_loans_owner_org", table_name="plate_loans")
    op.drop_index("ix_plate_loans_ws_status", table_name="plate_loans")
    op.drop_table("plate_loans")
```

(No FK from `plate_loan_items.plate_id` to `registered_plates` — deliberate: loans reference plates loosely like the legacy system, closed-loan history must survive plate deletion. If the FK-coverage test insists on categorizing only *declared* FKs, only `loan_id` needs an entry.)

- [ ] **Step 2: ORM** `plate_loan_models.py` (mirror `shipment_models.py` exactly — mixins, `relationship(cascade="all, delete-orphan", passive_deletes=True, lazy="selectin")` for items; `LoanItemModel` has no version column).

- [ ] **Step 3: Repository** `plate_loan_repository.py` — subclass the same base as the shipment repo; `_to_domain`/`_to_model`/`_update_model` with wholesale `model.items = [self._item_to_model(i) for i in aggregate.items]` (preserving item ids, Shipment pattern). Query methods:

```python
    async def find_by_workspace(self, workspace_id, *, status=None, owner_org_id=None,
                                borrower_org_id=None, requested_by=None, plate_id=None,
                                overdue=False) -> list[PlateLoan]:
        stmt = select(PlateLoanModel).where(PlateLoanModel.workspace_id == workspace_id)
        if status is not None:
            stmt = stmt.where(PlateLoanModel.status == status)
        if owner_org_id is not None:
            stmt = stmt.where(PlateLoanModel.owner_org_id == owner_org_id)
        if borrower_org_id is not None:
            stmt = stmt.where(PlateLoanModel.borrower_org_id == borrower_org_id)
        if requested_by is not None:
            stmt = stmt.where(PlateLoanModel.requested_by == requested_by)
        if plate_id is not None:
            stmt = stmt.where(
                PlateLoanModel.id.in_(
                    select(LoanItemModel.loan_id).where(LoanItemModel.plate_id == plate_id)
                )
            )
        if overdue:
            stmt = stmt.where(
                PlateLoanModel.status == LoanStatus.OPEN.value,
                PlateLoanModel.due_date.isnot(None),
                PlateLoanModel.due_date < date.today(),
            )
        stmt = stmt.order_by(PlateLoanModel.created_at.desc())
        ...

    async def active_plate_ids(self, workspace_id, plate_ids) -> set[uuid.UUID]:
        if not plate_ids:
            return set()
        stmt = (
            select(LoanItemModel.plate_id)
            .join(PlateLoanModel, LoanItemModel.loan_id == PlateLoanModel.id)
            .where(
                PlateLoanModel.workspace_id == workspace_id,
                LoanItemModel.plate_id.in_(plate_ids),
                LoanItemModel.status.in_([s.value for s in ACTIVE_LOAN_ITEM_STATUSES]),
            )
        )
        ...

    async def borrowed_plate_ids(self, workspace_id, borrower_org_id) -> set[uuid.UUID]:
        stmt = (
            select(LoanItemModel.plate_id)
            .join(PlateLoanModel, LoanItemModel.loan_id == PlateLoanModel.id)
            .where(
                PlateLoanModel.workspace_id == workspace_id,
                PlateLoanModel.borrower_org_id == borrower_org_id,
                LoanItemModel.status.in_([s.value for s in ACTIVE_LOAN_ITEM_STATUSES]),
            )
        )
        ...
```

Add `find_by_ids` to the plate repo (mirror `BatchRepository.find_by_ids`'s impl).

- [ ] **Step 4: Failing integration tests** — `test_plate_loan_repository.py` (separate UoWs per phase, fresh workspace uuid per test; mirror the S3 file's idioms). Cover: (a) round-trip with items + item statuses survive; (b) partial-unique violation — save loan A with plate P active, then loan B with P → `IntegrityError`; a CLOSED/RETURNED item does NOT block a new loan on the same plate; (c) `active_plate_ids` returns exactly the active subset (include a returned item + an unrelated plate as distractors); (d) `borrowed_plate_ids` filters by borrower org and active status; (e) `find_by_workspace(overdue=True)` returns only OPEN loans with `due_date < today` (one overdue, one due-tomorrow, one overdue-but-closed as distractors); (f) `find_by_workspace(plate_id=...)` finds the loan through its item; (g) wholesale item update: transition an item, save, reload — status + `status_changed_at` persisted, version bumped once.

- [ ] **Step 5: Run.** `make migrate`; `cd backend && uv run pytest tests/integration/inventory/test_plate_loan_repository.py -q` — PASS; `uv run alembic downgrade 062_plate_groups && uv run alembic upgrade head` — both succeed; `uv run pytest tests/unit -q` — baseline only (fix the FK-coverage gate per the Files note if it flags `fk_loan_items_loan`).

- [ ] **Step 6: Commit.**

```bash
git commit -m "feat(persistence): plate_loans + items (migration 063), loan repository, plate find_by_ids" -- backend/alembic/versions/063_plate_loans.py backend/src/cellar/infrastructure/persistence/sqlalchemy/inventory/plate_loan_models.py backend/src/cellar/infrastructure/persistence/sqlalchemy/inventory/plate_loan_repository.py backend/src/cellar/infrastructure/persistence/sqlalchemy/inventory/registered_plate_repository.py backend/src/cellar/domain/inventory/repository.py backend/tests/unit/cascade/test_fk_coverage.py backend/tests/integration/inventory/test_plate_loan_repository.py
```

---

### Task 4: Authority foundation — the repo's first runtime `check_action`

**Files:**
- Modify: `backend/src/cellar/application/auth.py` (`check_action` on the protocol + `require_loan_authority`)
- Modify: `backend/src/cellar/infrastructure/duar/auth.py` (`SERVICE_ACTIONS` entry)
- Modify: `backend/tests/fakes/fake_auth.py` (`granted_actions` + async `check_action`)
- Test: `backend/tests/unit/test_auth_guards.py` (extend the existing guard test file — find it; if guards are tested elsewhere, e.g. `tests/unit/application/test_auth.py`, use that file)

**Interfaces:**
- Consumes: SDK `RequestAuth.check_action(action: str) -> bool` (async, per-request-deduped — verified present in duar_auth 0.20).
- Produces: `AuthContext` protocol gains `async def check_action(self, action: str) -> bool: ...`; new guard `async def require_loan_authority(auth, owner_org_id)` (owner-side verbs) and constant `LOAN_APPROVE_ACTION = "cellar:approve_loan"` (exported from `application/auth.py` — the action string lives with the guard, not per-use-case); `FakeAuth(granted_actions={"cellar:approve_loan"})` in tests. Task 6 consumes the guard.

- [ ] **Step 1: Failing tests** (in the guard test file):

```python
class TestRequireLoanAuthority:
    async def test_admin_bypasses_org_and_action(self) -> None:
        auth = FakeAuth(role="admin", org_id=uuid.uuid4(), granted_actions=set())
        await require_loan_authority(auth, uuid.uuid4())  # no raise

    async def test_owner_org_member_with_action_passes(self) -> None:
        org = uuid.uuid4()
        auth = FakeAuth(role="editor", org_id=org, granted_actions={LOAN_APPROVE_ACTION})
        await require_loan_authority(auth, org)

    async def test_owner_org_member_without_action_forbidden(self) -> None:
        org = uuid.uuid4()
        auth = FakeAuth(role="editor", org_id=org, granted_actions=set())
        with pytest.raises(AuthorizationError):
            await require_loan_authority(auth, org)

    async def test_foreign_org_member_forbidden_even_with_action(self) -> None:
        auth = FakeAuth(role="editor", org_id=uuid.uuid4(), granted_actions={LOAN_APPROVE_ACTION})
        with pytest.raises(AuthorizationError):
            await require_loan_authority(auth, uuid.uuid4())

    async def test_viewer_forbidden(self) -> None:
        org = uuid.uuid4()
        auth = FakeAuth(role="viewer", org_id=org, granted_actions={LOAN_APPROVE_ACTION})
        with pytest.raises(AuthorizationError):
            await require_loan_authority(auth, org)
```

Run — FAIL (imports).

- [ ] **Step 2: Implement.** In `application/auth.py`: add to the `AuthContext` Protocol body `async def check_action(self, action: str) -> bool: ...` (with a docstring noting the SDK dedupes per request), then:

```python
LOAN_APPROVE_ACTION = "cellar:approve_loan"


async def require_loan_authority(
    auth: AuthContext | None, owner_org_id: uuid.UUID
) -> None:
    """Owner-side loan verbs (approve/deny/confirm-out/confirm-in).

    Admin/owner bypasses everything (also dodges the ungranted-action
    deadlock — no Sentinel grants exist until an operator assigns them).
    Otherwise: editor in the OWNER org holding the cellar:approve_loan
    RBAC action — the first runtime check_action call in this codebase.
    """
    require_authenticated(auth)  # user-attributed action (approved_by) — no system bypass
    require_editor(auth)
    assert auth is not None  # require_authenticated raised otherwise
    if auth.is_admin:
        return
    if auth.org_id != owner_org_id:
        raise AuthorizationError("Only the owner organization can manage this loan")
    if not await auth.check_action(LOAN_APPROVE_ACTION):
        raise AuthorizationError("Missing loan approval permission")
```

In `infrastructure/duar/auth.py`, append to `SERVICE_ACTIONS`:

```python
    {"action": "cellar:approve_loan", "description": "Approve and manage plate loan requests"},
```

In `tests/fakes/fake_auth.py`, add ctor kwarg `granted_actions: set[str] | None = None` (stored as-is) and:

```python
    async def check_action(self, action: str) -> bool:
        # None = permissive default (legacy fixtures never think about actions);
        # pass an explicit set to test denial paths.
        return True if self._granted_actions is None else action in self._granted_actions
```

(Adapt attribute naming to the file's style.) If mypy/import-linter flags the protocol change against other structural implementers (S1's `_AuthShim` in export row_streams — the known protocol-widener sweep!), extend EVERY structural `AuthContext` implementer with the same async method (grep for classes with `workspace_role`/`has_role` used as auth: `_AuthShim`, the S3 verify rig is scratchpad-only, any others the type checker names). This is the S1 final-review lesson: protocol wideners must sweep ALL structural implementers.

- [ ] **Step 3: Run.** `cd backend && uv run pytest tests/unit -q` — PASS (baseline only); `make lint` (import-linter) — clean.

- [ ] **Step 4: Commit.**

```bash
git commit -m "feat(auth): cellar:approve_loan action + require_loan_authority (first runtime check_action)" -- backend/src/cellar/application/auth.py backend/src/cellar/infrastructure/duar/auth.py backend/tests/fakes/fake_auth.py backend/tests/unit
```

(Adjust the tests pathspec to the actual guard-test file touched.)

---

### Task 5: Application — barcode resolver, RequestPlateLoan, ListLoans/GetLoan

**Files:**
- Create: `backend/src/cellar/application/inventory/barcode_resolution.py`
- Create: `backend/src/cellar/application/inventory/plate_loans.py` (commands/queries + Request/List/Get; Task 6 appends the transition use cases)
- Modify: `backend/src/cellar/infrastructure/di/_inventory.py`, `backend/src/cellar/interface/dependencies/_inventory.py` (+ exports)
- Test: `backend/tests/unit/test_barcode_resolution.py` (new)

**Interfaces:**
- Consumes: Tasks 2-4; `PlateVisibilityService`; `OrgPlatePolicyRepository` (get-or-default policy).
- Produces (Task 8 imports these): `RequestPlateLoanCommand{workspace_id, requested_by, plate_ids: list[uuid]|None, barcodes: list[str]|None, group_id: uuid|None, due_date: date|None, notes: str|None}` (exactly one of plate_ids/barcodes/group_id), `ListLoansQuery{workspace_id, status: str|None, owner_org_id: uuid|None, borrower_org_id: uuid|None, requested_by: uuid|None, plate_id: uuid|None, overdue: bool}`, `GetLoanQuery{workspace_id, loan_id}`; use cases `RequestPlateLoan`, `ListLoans`, `GetLoan`; DTO `LoanWithPlates{loan: PlateLoan, plates: dict[uuid, RegisteredPlate]}` (List/Get return it so routes can render barcodes — never UUIDs); pure `barcode_candidates(raw: str) -> list[str]`.

**Barcode resolver (spec §7)** — `barcode_resolution.py`:

```python
"""Barcode scan/paste resolution — spec §7 fallback chain.

Exact match first; only when that misses: all-digits inputs shorter than 6
are left-padded with '0' to width 6 (legacy str_pad convention), then a
strip-leading-zeros variant. First hit wins (barcodes are workspace-unique,
so the chain is deterministic). Shared by loan requests now, kiosk scan in S5.
"""

from __future__ import annotations

import uuid

from cellar.domain.inventory.registered_plate import RegisteredPlate
from cellar.domain.inventory.repository import RegisteredPlateRepository


def barcode_candidates(raw: str) -> list[str]:
    cleaned = raw.strip()
    if not cleaned:
        return []
    candidates = [cleaned]
    if cleaned.isdigit() and len(cleaned) < 6:
        candidates.append(cleaned.zfill(6))
    stripped = cleaned.lstrip("0")
    if stripped and stripped != cleaned:
        candidates.append(stripped)
    return candidates


async def resolve_barcode(
    repo: RegisteredPlateRepository, workspace_id: uuid.UUID, raw: str
) -> RegisteredPlate | None:
    for candidate in barcode_candidates(raw):
        plate = await repo.find_by_barcode(workspace_id, candidate)
        if plate is not None:
            return plate
    return None
```

Unit tests (`test_barcode_resolution.py`): candidates for `"5261"` → `["5261", "005261"]`; `"005261"` → `["005261", "5261"]`; `"BC-01"` → `["BC-01"]`; `"  005261 "` strips; `""`/`"   "` → `[]`; `"0"` → `["0", "000000"]` (stripped variant `""` excluded); plus an async `resolve_barcode` test with a stub repo proving first-hit-wins order.

**RequestPlateLoan** — behavior (write the full class in the established S3 style: guards → uow → checks → mutate → commit → dispatch):

1. `require_editor(auth)`; `require_same_workspace`. `borrower_org_id = auth.org_id`; None → `ValidationError("Caller has no organization — loans require an org")`.
2. Mode validation: exactly one of `plate_ids`/`barcodes`/`group_id` provided, else `ValidationError`.
3. Resolve plates (inside the uow): `plate_ids` → `plate_repo.find_by_ids` (any missing id → `NotFoundError` on that id); `barcodes` → per-barcode `resolve_barcode`, collecting misses; `group_id` → group repo `find_by_id_in_workspace` (404-hidden==missing via `can_view_owner`) then `plate_repo.search(workspace_id, group_id=...)` (empty group → `ValidationError("Group has no plates")`).
4. Visibility: `excluded = await visibility.excluded_org_ids(...)`; any resolved plate failing `can_view` is reported EXACTLY like a miss (barcode mode: add to the misses list; id mode: `NotFoundError`) — no existence oracle. Barcode misses → `ValidationError("Unknown barcodes: 'X', 'Y'")` listing all.
5. All plates must share one NON-NULL `owner_org_id` → else `ValidationError` ("Plates span multiple organizations" / "Plate 'B' has no owner organization — set ownership before loaning").
6. Active-item conflict: `active = await loan_repo.active_plate_ids(ws, [p.id ...])`; non-empty → `ConflictError("Plates already on an active loan: '<barcodes>'")` (these plates are visible to the caller by this point — naming them is safe).
7. Policy: `policy = await policy_repo.find_by_org(ws, owner_org_id) or OrgPlatePolicy.create_default(...)`; `due = input.due_date or (date.today() + timedelta(days=policy.default_due_days)) if policy.default_due_days else input.due_date`; `loan = PlateLoan.request(..., auto_approved=not policy.require_approval, due_date=due)`; if `not policy.require_approval and policy.confirmation == LoanConfirmationMode.NONE:` → `loan.confirm_checkout(loan.eligible_item_ids(LoanItemStatus.CHECKED_OUT))` (full self-serve).
8. `loan_repo.save(loan)`; commit; dispatch. Race on the partial unique index surfaces as `IntegrityError` from commit — accepted backstop (S2 T4 precedent), do not catch.

**ListLoans / GetLoan** — `require_workspace_role(auth, "viewer")`; loan visibility rule: with `excluded = await visibility.excluded_org_ids(...)`, a loan is visible iff `loan.owner_org_id not in excluded or loan.borrower_org_id == auth.org_id`. `GetLoan` 404s invisible loans (hidden==missing); `ListLoans` filters them out post-query. Both then batch-fetch plates: `plate_repo.find_by_ids(ws, all item plate_ids)` → `LoanWithPlates(loan, {p.id: p})` (missing plates — deleted since — simply absent from the dict; routes fall back to a "deleted plate" label).

**DI:** `# --- Plate Loans ---` section in `di/_inventory.py` mirroring the plate-groups factories (one `AsyncUnitOfWork` per factory shared by loan repo + plate repo + policy repo + `PlateVisibilityService`); Dep aliases `RequestPlateLoanDep/ListLoansDep/GetLoanDep` in `dependencies/_inventory.py` + exports.

- [ ] **Step 1:** Write the failing `test_barcode_resolution.py`; run — FAIL (module missing).
- [ ] **Step 2:** Implement `barcode_resolution.py`; unit tests PASS.
- [ ] **Step 3:** Implement `plate_loans.py` (commands/queries/DTO + the three use cases exactly per the behavior specs above, matching `plate_groups.py`'s structure), then DI + Deps.
- [ ] **Step 4:** `uv run pytest tests/unit -q` PASS; `uv run python -c "from cellar.infrastructure.di.container import create_container; create_container()"` (or `make lint` fallback) — clean. (Use-case behavior is API-tested in Task 8 — same split as S3.)
- [ ] **Step 5: Commit.**

```bash
git commit -m "feat(application): RequestPlateLoan + barcode resolver (spec §7) + loan list/get" -- backend/src/cellar/application/inventory/barcode_resolution.py backend/src/cellar/application/inventory/plate_loans.py backend/src/cellar/infrastructure/di/_inventory.py backend/src/cellar/interface/dependencies/_inventory.py backend/src/cellar/interface/dependencies/__init__.py backend/tests/unit/test_barcode_resolution.py
```

---

### Task 6: Application — item-transition use cases

**Files:**
- Modify: `backend/src/cellar/application/inventory/plate_loans.py` (append)
- Modify: `backend/src/cellar/infrastructure/di/_inventory.py`, `backend/src/cellar/interface/dependencies/_inventory.py` (+ exports)

**Interfaces:**
- Consumes: Task 4's `require_loan_authority`; Task 5's loan-visibility rule (extract the shared `_loan_visible(loan, auth, excluded) -> bool` helper when this task starts if Task 5 inlined it).
- Produces (Task 8 imports): `LoanItemsCommand{workspace_id, loan_id, item_ids: list[uuid] | None}` (None = all eligible) shared by all six; use cases `ApproveLoanItems`, `DenyLoanItems`, `ConfirmLoanCheckout`, `RequestLoanReturn`, `ConfirmLoanReturn`, `CancelLoanItems` — each returns `Result[LoanWithPlates, DomainError]`.

**Shared skeleton** (write ONE private base in `plate_loans.py`, six thin subclasses — the verbs differ only in: authority guard, domain method, target status for eligible-expansion, and post-collapse):

```python
class _LoanItemsUseCase:
    """Shared machinery: load loan (hidden==missing), authority, expand
    item_ids=None to all-eligible, run the verb, apply policy collapse,
    save, enrich with plates."""

    _target: LoanItemStatus  # subclass sets

    def __init__(self, uow, repo, plate_repo, policy_repo, dispatcher, visibility): ...

    async def __call__(self, input: LoanItemsCommand, auth=None) -> Result[LoanWithPlates, DomainError]:
        require_editor(auth)
        require_same_workspace(auth, input.workspace_id)
        async with self._uow:
            loan = await self._repo.find_by_id_in_workspace(input.workspace_id, input.loan_id)
            if loan is None:
                return Failure(NotFoundError("PlateLoan", str(input.loan_id)))
            excluded = await self._visibility.excluded_org_ids(input.workspace_id, auth)
            if not _loan_visible(loan, auth, excluded):
                return Failure(NotFoundError("PlateLoan", str(input.loan_id)))
            await self._authorize(auth, loan)
            item_ids = input.item_ids if input.item_ids is not None else loan.eligible_item_ids(self._target)
            if not item_ids:
                return Failure(ValidationError("No eligible loan items"))
            self._apply(loan, item_ids, auth)
            await self._collapse(loan, item_ids)
            await self._repo.save(loan)
            events = await self._uow.commit()
            # Enrich INSIDE the block — the UoW session closes on exit and
            # a post-block repo call raises RuntimeError (post-commit reads
            # after commit() are fine; the session is still open).
            result = await self._enrich(loan)
        await self._dispatcher.dispatch_all(events)
        return Success(result)
```

Per-verb specifics:
- **Approve** (`_target=APPROVED`): `_authorize` = `await require_loan_authority(auth, loan.owner_org_id)`; `_apply` = `loan.approve_items(item_ids, approved_by=auth.user_id)`; `_collapse` = if owner policy `confirmation == NONE`: `loan.confirm_checkout([i for i in item_ids if <still APPROVED>])` — expand via `loan.eligible_item_ids(CHECKED_OUT)` intersected with `item_ids`.
- **Deny** (`DENIED`): owner authority; no collapse.
- **ConfirmCheckout** (`CHECKED_OUT`): owner authority; no collapse.
- **RequestReturn** (`RETURN_PENDING`): borrower-side — `_authorize` = raise `AuthorizationError` unless `auth.is_admin or auth.org_id == loan.borrower_org_id`; collapse: owner policy `confirmation == NONE` → `loan.confirm_return(...)` same intersection pattern.
- **ConfirmReturn** (`RETURNED`): owner authority; no collapse.
- **Cancel** (`CANCELLED`): borrower-side (same rule as RequestReturn); no collapse.

Policy fetch for collapse: `policy_repo.find_by_org(ws, loan.owner_org_id) or create_default` — fetch once in `_collapse` only for the two verbs that need it.

**DI:** six factories + Deps (`ApproveLoanItemsDep` … `CancelLoanItemsDep`), same pattern.

- [ ] **Step 1:** Implement (no new unit tests — the machine is unit-tested in Task 2, authority in Task 4; the wiring matrix is Task 8's API tests, same split as S3).
- [ ] **Step 2:** `uv run pytest tests/unit -q` PASS; container-resolution sanity as in Task 5.
- [ ] **Step 3: Commit.**

```bash
git commit -m "feat(application): loan item transition use cases (approve/deny/checkout/return/cancel) with policy collapse" -- backend/src/cellar/application/inventory/plate_loans.py backend/src/cellar/infrastructure/di/_inventory.py backend/src/cellar/interface/dependencies/_inventory.py backend/src/cellar/interface/dependencies/__init__.py
```

---

### Task 7: Borrowed-plate READ visibility (spec §5 loan clause)

**Files:**
- Modify: `backend/src/cellar/application/inventory/plate_visibility.py` (`borrowed_plate_ids` + `can_view` extension)
- Modify: `backend/src/cellar/application/inventory/registered_plates.py` (`GetPlate`, `ListPlates`, `ListChildren` wire the borrowed set)
- Modify: `backend/src/cellar/domain/inventory/repository.py` + `registered_plate_repository.py` (`search(..., include_plate_ids: set[uuid] | None = None)`)
- Modify: `backend/src/cellar/infrastructure/persistence/sqlalchemy/inventory/plate_read_model_reader.py` + its route caller `interface/routes/molecules.py` (molecule→plates read model)
- Modify: `backend/src/cellar/infrastructure/di/_screening.py` (plate use-case factories now also build the loan repo for the visibility service)

**Interfaces:**
- Produces: `PlateVisibilityService.__init__(policy_repo, loan_repo: PlateLoanRepository | None = None)`; `async def borrowed_plate_ids(self, workspace_id, auth) -> set[uuid.UUID]` (empty when no loan_repo/auth/org); `can_view(plate, auth, excluded, borrowed: set[uuid.UUID] = frozenset())` → `self.can_view_owner(...) or plate.id in borrowed`. Existing callers compile unchanged (defaulted params); ONLY the read surfaces pass a real borrowed set.

**Scope decision (Global Constraints #3):** read surfaces only — GetPlate, ListPlates, ListChildren, molecule→plates read model. Write paths (update/map-wells/status/derive/delete), export, tag verbs, groups stay strict: borrowers see, owners modify. Update the service's class docstring: the S2 seam note ("extend excluded_org_ids callers there, not here") is now RESOLVED — the loan clause lives in the service (the repo exists now); write-path callers simply don't pass the borrowed set, and a comment in the docstring records that narrowing deliberately.

- [ ] **Step 1:** Extend the service (borrowed set via `loan_repo.borrowed_plate_ids(ws, auth.org_id)` when both repo and `auth.org_id` present, else `set()`); extend `can_view`; keep `can_view_owner` untouched (groups stay strict).
- [ ] **Step 2:** `search(..., include_plate_ids=...)`: the exclusion clause becomes `or_(owner IS NULL, owner NOT IN excluded, id IN include_plate_ids)` — mirror the existing composition style; only append the `id IN` arm when the set is non-empty (same empty-IN gotcha as S2's expanding bindparam — check how `exclude_owner_org_ids` handles empties in this method and match).
- [ ] **Step 3:** Wire the three use cases: each fetches `borrowed = await self._visibility.borrowed_plate_ids(...)` alongside `excluded` and passes it to `can_view`/`search`. Read-model route (`molecules.py` caller) + reader gain the same optional include-set param.
- [ ] **Step 4:** DI: in `_screening.py`'s plate section, construct `PlateVisibilityService(SQLAlchemyOrgPlatePolicyRepository(uow), SQLAlchemyPlateLoanRepository(uow))` for the three read use cases (others may keep the 1-arg form — simplest: pass the loan repo everywhere, unused args are harmless). Same for the `PlateVisibilityUoWDep` factory in `interface/dependencies/_inventory.py` and the plate-groups factories in `di/_inventory.py` (groups don't consume borrowed, but the ctor signature is shared — defaulted param means NO change needed there; touch only what the type checker forces).
- [ ] **Step 5:** `uv run pytest tests/api/test_registered_plates.py tests/api/test_plate_groups.py -q` — no regressions (behavioral proof of the new clause lands in Task 8's API tests). `uv run pytest tests/unit -q` — baseline.
- [ ] **Step 6: Commit.**

```bash
git commit -m "feat(visibility): borrowed plates readable by borrower org (spec §5 loan clause, read surfaces)" -- backend/src/cellar/application/inventory/plate_visibility.py backend/src/cellar/application/inventory/registered_plates.py backend/src/cellar/domain/inventory/repository.py backend/src/cellar/infrastructure/persistence/sqlalchemy/inventory/registered_plate_repository.py backend/src/cellar/infrastructure/persistence/sqlalchemy/inventory/plate_read_model_reader.py backend/src/cellar/interface/routes/molecules.py backend/src/cellar/infrastructure/di/_screening.py backend/src/cellar/interface/dependencies/_inventory.py
```

---

### Task 8: API routes + API tests

**Files:**
- Create: `backend/src/cellar/interface/routes/plate_loans.py`
- Modify: `backend/src/cellar/interface/app.py` + `backend/tests/api/conftest.py::_create_test_app()` (BOTH registrations; also: conftest fixtures need `granted_actions` plumbed — see Step 1 note)
- Test: `backend/tests/api/test_plate_loans.py` (new)

**Interfaces:**
- Consumes: Tasks 5-7 exports.
- Produces: routes `POST /api/v1/plate-loans` (201), `GET ""` (filters `status`, `owner_org_id`, `borrower_org_id`, `mine: bool` [→ requested_by=auth.user_id], `plate_id`, `overdue: bool`), `GET /{loan_id}`, and six verb routes `POST /{loan_id}/items:approve|deny|confirm-out|request-return|confirm-in|cancel` (colon-verb paths per spec §10; FastAPI accepts literal colons in path segments — verify with one test first, fall back to `/{loan_id}/items/approve` ONLY if colon paths genuinely fail routing, and record the deviation). Response models colocated:

```python
class LoanItemResponse(BaseModel):
    id: uuid.UUID
    plate_id: uuid.UUID
    barcode: str          # from the LoanWithPlates map; "(deleted plate)" fallback
    plate_label: str      # same fallback ""
    status: LoanItemStatus
    status_changed_at: datetime


class LoanResponse(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    owner_org_id: uuid.UUID
    borrower_org_id: uuid.UUID
    requested_by: uuid.UUID
    approved_by: uuid.UUID | None = None
    due_date: date | None = None
    notes: str | None = None
    status: LoanStatus
    closed_at: datetime | None = None
    created_at: datetime
    items: list[LoanItemResponse]
    version: int

    @classmethod
    def from_dto(cls, dto: LoanWithPlates) -> LoanResponse: ...  # maps items via dto.plates
```

  Bodies: `RequestLoanBody{plate_ids: list[uuid]|None, barcodes: list[str]|None, group_id: uuid|None, due_date: date|None, notes: str|None}` (`extra: "forbid"`); `LoanItemsBody{item_ids: list[uuid] | None = None}`.

- [ ] **Step 1: Failing API tests** — `backend/tests/api/test_plate_loans.py`. Fixture note: the conftest's module-level clients are built once — for authority tests, construct FakeAuth variants inline following the existing `editor_client_own_org` fixture pattern, adding `granted_actions` kwargs: add TWO new fixtures to `tests/api/conftest.py` mirroring `editor_client_own_org` exactly — `approver_client_own_org` (`granted_actions={"cellar:approve_loan"}`) and keep `editor_client_own_org` as the no-action editor (pass `granted_actions=set()` to it ONLY if its FakeAuth currently defaults permissive and authority tests need denial — check FakeAuth's default from Task 4: `None` = permissive, so `editor_client_own_org` with default None would PASS action checks; to test denial add `denied_editor_client_own_org` with `granted_actions=set()`). Local helpers `_mk_plate` / `_set_policy(client, org, **fields)` copied from the S3 test style. Coverage matrix (each its own test):
  - **Request modes:** by `plate_ids`; by `barcodes` incl. a SHORT form (`"5261"` resolves plate `005261` — proves the §7 padding chain); by `group_id` (uses S3 seed helpers: make group, assign plates); exactly-one-mode 422; unknown barcode 422 listing it; empty group 422.
  - **Ownership/org:** plates spanning two orgs 422; NULL-owner plate 422; borrower recorded = caller's org.
  - **Policy collapse:** default policy → items REQUESTED; `require_approval=false` → items APPROVED; `require_approval=false + confirmation=none` → items CHECKED_OUT straight away; `default_due_days=7` fills `due_date` (assert `date.today()+7`); explicit `due_date` wins.
  - **Active conflict:** second loan on an active plate → 409 naming the barcode; a RETURNED plate can be re-loaned (200).
  - **Authority matrix:** approve as admin (200); as owner-org editor WITH action (200, via `approver_client_own_org`); as owner-org editor WITHOUT action (403); as borrower-org editor with action but wrong org (403 — use `editor_client_other_org` with granted action if the fixture allows, else construct); deny/confirm-out/confirm-in same guard (spot-check one each); request-return as borrower-org editor (200) and as unrelated-org editor (403); cancel as requester (200).
  - **Machine via API:** full happy path request→approve→confirm-out→request-return→confirm-in, asserting item statuses + loan CLOSED + `closed_at`; `item_ids: null` = all-eligible expansion; invalid transition 422; approve on already-approved 422.
  - **Collapse on transitions:** policy `confirmation=none` (require_approval default true) → approve auto-advances to CHECKED_OUT; request-return auto-advances to RETURNED.
  - **Filters:** `mine=true` returns only my requests; `status=open`; `overdue=true` (PATCH a loan's due_date via direct SQL helper or create with explicit past due_date — creating with a past `due_date` is allowed and simplest); `plate_id=`.
  - **Loan visibility:** private owner org's loan invisible (404/absent) to unrelated org, visible to borrower org and to members of the owner org — arrange with `_set_policy(plates_private=True)` + `finally` reset (S3 pattern).
  - **Borrowed-plate visibility (Task 7 proof):** owner org private; plate on active loan to MY org → `GET /api/v1/plates/{id}` 200 and it appears in `GET /api/v1/plates`; after confirm-return (loan closed) → 404 again; a private-org plate NOT on loan stays 404 throughout.

Run: `cd backend && uv run pytest tests/api/test_plate_loans.py -q` — FAIL (404s).

- [ ] **Step 2: Implement the router** (thin handlers per S3 style: build command → `result_to_response(await uc(...))` → `LoanResponse.from_dto`; `mine=true` maps to `requested_by=auth.user_id`; declare the six verb routes with literal colon paths). Register in `app.py` + `_create_test_app()`.
- [ ] **Step 3:** Tests PASS; `uv run pytest tests/api/test_registered_plates.py tests/api/test_plate_groups.py tests/api/test_org_plate_policies.py -q` — no regressions.
- [ ] **Step 4: Commit.**

```bash
git commit -m "feat(api): /api/v1/plate-loans — request, item verbs, filters + authority/policy/visibility test matrix" -- backend/src/cellar/interface/routes/plate_loans.py backend/src/cellar/interface/app.py backend/tests/api/conftest.py backend/tests/api/test_plate_loans.py
```

---

### Task 9: Orval regen + FE loan hooks

**Files:**
- Regenerate: `frontend/src/shared/lib/api/model/**`, `endpoints.ts`
- Modify: `frontend/src/features/inventory/hooks/query-keys.ts` (`LOANS_KEY`)
- Create: `frontend/src/features/inventory/hooks/use-plate-loans.ts`
- Test: `frontend/src/features/inventory/hooks/use-plate-loans.test.tsx`

**Interfaces:**
- Produces (Tasks 10-11 import): aliases `PlateLoan = LoanResponse`, `PlateLoanItem = LoanItemResponse`, value re-exports `LoanStatus`, `LoanItemStatus` (generated const-object unions); `LOANS_KEY`; `useLoans(filters?: {status?, mine?, owner_org_id?, borrower_org_id?, plate_id?, overdue?}, opts?: {enabled?})` (query key `[...LOANS_KEY, filters ?? {}]`); `useLoan(loanId, opts?)`; `useRequestLoan()` (vars = `RequestLoanBody`); `useLoanItemsAction()` — ONE mutation hook `mutate({loanId, verb, itemIds})` where `verb: "approve"|"deny"|"confirm-out"|"request-return"|"confirm-in"|"cancel"` posts `/plate-loans/${loanId}/items:${verb}` body `{item_ids: itemIds ?? null}`; success invalidates `LOANS_KEY` + `PLATES_KEY` and toasts per-verb (`"Items approved"` etc. via a verb→message map).
- Regen recipe: same as S3 Task 7 (make dev-be, wait for openapi.json, `/Users/sidx/Library/pnpm/pnpm generate:api`, `make stop`).

- [ ] **Step 1:** Regen; confirm `loanResponse.ts`/`loanItemResponse.ts`/`loanStatus.ts`/`loanItemStatus.ts`/`requestLoanBody.ts` exist.
- [ ] **Step 2:** Failing hook tests (mirror `use-plate-groups.test.tsx` incl. `beforeEach(vi.clearAllMocks)`): useLoans passes filters as params (booleans included only when set — assert `params` shape); useRequestLoan POSTs the body; useLoanItemsAction hits `/items:approve` with `{item_ids: null}` when itemIds omitted and invalidates both keys (assert via `qc.invalidateQueries` spy or a mounted useLoans refetch).
- [ ] **Step 3:** Implement; tests PASS; `exec tsc --noEmit` exit 0.
- [ ] **Step 4: Commit** (`git add frontend/src/shared/lib/api` + pathspec commit of the api dir, query-keys, hook + test — NEVER package.json/pnpm-lock.yaml/next-env.d.ts).

```bash
git commit -m "feat(frontend): plate-loan hooks + orval regen" -- frontend/src/shared/lib/api frontend/src/features/inventory/hooks/query-keys.ts frontend/src/features/inventory/hooks/use-plate-loans.ts frontend/src/features/inventory/hooks/use-plate-loans.test.tsx
```

---

### Task 10: FE Loans page — tabs, loan list/detail, request dialog (3 modes + template)

**Files:**
- Create: `frontend/src/app/(dashboard)/inventory/loans/page.tsx` (3-line wrapper → `LoanDashboard`)
- Create: `frontend/src/features/inventory/components/loan-dashboard.tsx`
- Create: `frontend/src/features/inventory/components/loan-card.tsx` (one loan: header + items table + verb buttons)
- Create: `frontend/src/features/inventory/components/request-loan-dialog.tsx`
- Modify: `frontend/src/shared/lib/navigation.ts` (Inventory group: `{ title: "Loans", href: "/inventory/loans", icon: ArrowLeftRight }` after "Plate Groups")
- Modify: `frontend/src/shared/lib/status-variants.ts` (loan item statuses — see Task 11 notes; do it here if Task 11 hasn't run)
- Test: `frontend/src/features/inventory/components/request-loan-dialog.test.tsx`

**UX (locked):**
- `LoanDashboard`: `PageHeader(title="Loans", subtitle="Plate checkout requests and approvals")` + "Request loan" Button (right side); shadcn `Tabs` via `useHashTab("mine")`: **My requests** (`useLoans({mine: true})`), **Approvals** (`useLoans({status: "open", owner_org_id: me.org_id})` — gated on `useCurrentUser` with the S3 meFailed fallback pattern; tab hidden entirely when org unresolved), **All** (`useLoans()`), plus an "Overdue" filter Switch on the All tab (`overdue: true`). Each tab renders a vertical list of `LoanCard`s (loans are low-volume — no grid).
- `LoanCard`: header row = borrower org name → owner org name (via `useOrgs`), `StatusBadge` for loan status, due date (red text when past-due + open), requested-by shown as "you" when it's me else omitted (no user directory — do NOT render the UUID), notes line. Items table: barcode (mono) + label + `StatusBadge(item.status)` + per-item checkbox. Verb buttons under the table, shown by CONTEXT: approvals context (`canApprove` prop) → Approve / Deny / Confirm hand-out / Confirm return; my-requests context → Request return / Cancel. Buttons act on checked items, or ALL eligible when none checked; label carries the count next to the verb: `Approve (2)`. All verbs → `useLoanItemsAction`. Disable while pending. `canApprove` = admin `me` OR `me.org_id === loan.owner_org_id` (server enforces the action grant — a 403 toast is acceptable UX for an ungranted member; do not attempt to mirror check_action client-side).
- `RequestLoanDialog`: Tabs for the three modes — **From group** (Select of flattened `usePlateGroupTree(me.org)` names → on submit send `group_id`; hint text shows the group's plate count), **Paste barcodes** (Textarea, one per line → `barcodes`), **CSV** (`<input type="file">` + `FileReader` → `parseCsvRows` → first column as barcodes; "Download Template" Button → `saveText("Barcode\n005261\n003251\n", "loan_request_template.csv")`). Shared fields: due date (`<Input type="date">`, empty = server default from policy), notes (Textarea). Submit disabled until the active mode has input; on 422 the global error toast surfaces the unknown-barcode list (server message). Success closes + toast (hook does the toast).

- [ ] **Step 1: Failing dialog test** — `request-loan-dialog.test.tsx` (Radix polyfill block verbatim; mock customInstance + toast): (a) paste mode: type two lines, submit → POST body `{barcodes: ["005261", "5261"], group_id: null, plate_ids: null, ...}` (or fields omitted — match the implementation's body shape exactly); (b) submit disabled with no input; (c) template button triggers a download (mock `saveText` from `@/shared/lib/api/download` and assert called with a string starting `"Barcode"`); (d) CSV mode parses a File and submits its barcodes (construct a `File` with `new File(["Barcode\n005261\n"], "x.csv")`; if jsdom FileReader timing is flaky, drive the internal parse handler directly — keep ONE robust assertion, not a flaky three).
- [ ] **Step 2:** Implement the four components + nav; wire dialog open state in `LoanDashboard`.
- [ ] **Step 3:** `exec vitest run src/features/inventory` PASS; `exec tsc --noEmit` 0; `exec biome check src/features/inventory src/app/\(dashboard\)/inventory/loans src/shared/lib/navigation.ts` 0.
- [ ] **Step 4: Commit.**

```bash
git commit -m "feat(frontend): Loans page — tabs, loan cards with item verbs, 3-mode request dialog + CSV template" -- frontend/src/app frontend/src/features/inventory/components/loan-dashboard.tsx frontend/src/features/inventory/components/loan-card.tsx frontend/src/features/inventory/components/request-loan-dialog.tsx frontend/src/features/inventory/components/request-loan-dialog.test.tsx frontend/src/shared/lib/navigation.ts frontend/src/shared/lib/status-variants.ts
```

---

### Task 11: Custody chips (plates list) + loan history (plate detail)

**Files:**
- Modify: `frontend/src/features/inventory/components/plate-list.tsx` (Custody column)
- Modify: `frontend/src/features/inventory/components/plate-detail.tsx` (Loan history card)
- Modify: `frontend/src/shared/lib/status-variants.ts` (if Task 10 didn't already)
- Test: extend `frontend/src/features/inventory/components/plate-group-details.test.tsx`? No — new file `frontend/src/features/inventory/components/plate-custody.test.tsx` covering the custody-map helper.

**Design:**
- Custody map helper (exported from `use-plate-loans.ts`): `buildCustodyMap(loans: PlateLoan[]): Map<string, {loan: PlateLoan, item: PlateLoanItem}>` — active items only (`ACTIVE_LOAN_ITEM_STATUSES` mirrored as a const in the hooks file from the generated union values: `["requested","approved","checked_out","return_pending"]`).
- `plate-list.tsx`: `const { data: openLoans } = useLoans({ status: "open" });` + `custodyByPlate = useMemo(buildCustodyMap...)`; new column after Status: `headerName: "Custody"`, cellRenderer → nothing when unowned by a loan; else `<Badge variant=...>{orgName(borrower)} · due {due_date}</Badge>` with the item-status variant (e.g. requested → outline "Requested by <org>"). Keep it ONE chip — status nuance via the badge variant, not extra columns.
- `plate-detail.tsx`: append a "Loan History" `<Card>` (Daughter-Plates card shape): `useLoans({ plate_id: plateId })` rows — `{borrower org name} · {item status badge} · requested {created_at date} {due date if set}` — newest first (API already orders desc). Empty → "Never loaned." No per-loan navigation (loans page covers management).
- `status-variants.ts`: add keys `requested: "info"`, `approved: "active"`, `checked_out: "warning"`, `return_pending: "info"`, `denied: "error"`. `returned`/`cancelled` already exist app-wide — check their categories; if `returned`'s existing category reads wrong for loans (e.g. error-ish from shipments), do NOT change the global mapping (other domains own it) — instead pass an explicit `label`/variant at the loan call sites. Note whichever path was taken in the report.

- [ ] **Step 1:** Failing test for `buildCustodyMap` (pure function: active item wins, returned item ignored, newest loan wins if two somehow overlap).
- [ ] **Step 2:** Implement helper + both surfaces.
- [ ] **Step 3:** `exec vitest run src/features/inventory` PASS; tsc 0; biome 0.
- [ ] **Step 4: Commit.**

```bash
git commit -m "feat(frontend): custody chips on plates list + loan history on plate detail" -- frontend/src/features/inventory/components/plate-list.tsx frontend/src/features/inventory/components/plate-detail.tsx frontend/src/features/inventory/hooks/use-plate-loans.ts frontend/src/features/inventory/components/plate-custody.test.tsx frontend/src/shared/lib/status-variants.ts
```

---

### Task 12: Runtime verification (CONTROLLER-DRIVEN — not a subagent task)

Reuse the S3 verify rig (session memory has the recipe; the S3 scratchpad scripts are the template — recreate in this session's scratchpad):
- [ ] `serve_verify.py` variant: VerifyAuth gains `async def check_action(self, action): return True`; strip sentinel middleware as before; :8000.
- [ ] Seed a loan story via API: flip tamu policy `require_approval=true, confirmation=admin_confirm`; as public-org auth request a loan on 2 SAC1 plates (internal loan); approve one item, leave one requested; second loan with `require_approval=false, confirmation=none` policy org demonstrating self-serve CHECKED_OUT; one loan with past due_date for the overdue filter.
- [ ] Playwright walk (`verify_s4.mjs`): crafted-token login → Loans nav → My requests tab shows the loans; Approvals tab: approve remaining item (button count label), confirm hand-out; plates list shows custody chips with org NAME + due date; plate detail shows Loan History; request dialog: paste mode with a SHORT barcode (`5261`) succeeds (padding proof at the UI level); CSV template downloads; return flow to closure; overdue Switch filters. Screenshots: loans page, custody column, request dialog.
- [ ] Restore the real backend (`pkill serve_verify` + `make dev-be`) when done. Any defect → fix subagent → re-verify.

### Task 13: Final review, suites, ship (CONTROLLER-DRIVEN)

- [ ] Final whole-branch review (fable) with the accumulated-Minors triage list from the ledger; fix wave if needed; re-confirm.
- [ ] Full suites: backend (10-failure baseline), FE vitest, biome — by exit code.
- [ ] Spec-sync: append the four Global-Constraint deviations (action name, batch events, read-only borrowed visibility, admin action bypass) to spec §4.3/§5 as dated notes; `git add -f` the spec + this plan file; commit docs.
- [ ] Issue #71 comment (scope, commit range, screenshots noted); push; update `project_plate_tracker_port.md` memory (S4 shipped; S5 = kiosk + insights + S3/S4 polish intake; S6 = migration).

---

## Execution notes for the controller

- Model tiers: Tasks 1, 5 (resolver part) mechanical → cheap; Tasks 2, 3, 6 mid (sonnet); Task 4 protocol-widener → sonnet with the S1 `_AuthShim` sweep warning verbatim; Task 7 touches the S2 privacy surface → sonnet implement, **opus review**; Task 8 big matrix → sonnet; Tasks 10-11 UI → opus implement, sonnet review.
- Task 8's conftest change (fixtures with `granted_actions`) is the one cross-task file both 4 and 8 touch — sequence is safe (4 lands FakeAuth first).
- Colon-verb routes: if FastAPI path matching rejects `items:approve` literally, the fallback (slash paths) is a RECORDED spec deviation, not silent.
- `date.today()` in the overdue repo query is server-local; acceptable (matches `expiring_within_days` precedent).

