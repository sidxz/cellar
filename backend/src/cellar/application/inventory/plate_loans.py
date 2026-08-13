"""PlateLoan use cases — request a loan (spec §7), list/get with loan visibility (spec §8).

Task 6 appends the item-transition use cases (approve/deny/confirm-out/
confirm-in/cancel) to this same module.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, timedelta

from returns.result import Failure, Result, Success

from cellar.application.auth import (
    AuthContext,
    require_editor,
    require_same_workspace,
    require_workspace_role,
)
from cellar.application.inventory.barcode_resolution import resolve_barcode
from cellar.application.inventory.plate_visibility import PlateVisibilityService
from cellar.application.shared.command import Command
from cellar.application.shared.event_dispatcher import EventDispatcherProtocol
from cellar.application.shared.query import Query
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.inventory.enums import LoanConfirmationMode, LoanItemStatus
from cellar.domain.inventory.org_plate_policy import OrgPlatePolicy
from cellar.domain.inventory.plate_loan import PlateLoan
from cellar.domain.inventory.registered_plate import RegisteredPlate
from cellar.domain.inventory.repository import (
    OrgPlatePolicyRepository,
    PlateGroupRepository,
    PlateLoanRepository,
    RegisteredPlateRepository,
)
from cellar.domain.shared.errors import (
    ConflictError,
    DomainError,
    NotFoundError,
    ValidationError,
)

# ---------------------------------------------------------------------------
# Commands / Queries
# ---------------------------------------------------------------------------


@dataclass(frozen=True, kw_only=True)
class RequestPlateLoanCommand(Command):
    workspace_id: uuid.UUID
    requested_by: uuid.UUID
    plate_ids: list[uuid.UUID] | None = None
    barcodes: list[str] | None = None
    group_id: uuid.UUID | None = None
    due_date: date | None = None
    notes: str | None = None


@dataclass(frozen=True, kw_only=True)
class ListLoansQuery(Query):
    workspace_id: uuid.UUID
    status: str | None = None
    owner_org_id: uuid.UUID | None = None
    borrower_org_id: uuid.UUID | None = None
    requested_by: uuid.UUID | None = None
    plate_id: uuid.UUID | None = None
    overdue: bool = False


@dataclass(frozen=True, kw_only=True)
class GetLoanQuery(Query):
    workspace_id: uuid.UUID
    loan_id: uuid.UUID


# ---------------------------------------------------------------------------
# DTO + visibility helper (module level — Task 6 reuses both)
# ---------------------------------------------------------------------------


@dataclass
class LoanWithPlates:
    loan: PlateLoan
    plates: dict[uuid.UUID, RegisteredPlate]


def _loan_visible(loan: PlateLoan, auth: AuthContext | None, excluded: set[uuid.UUID]) -> bool:
    """Spec §8: owner-side visibility, plus the borrower can always see its
    own loans even when the owner org is otherwise private."""
    if loan.owner_org_id not in excluded:
        return True
    return auth is not None and loan.borrower_org_id == auth.org_id


def _loan_not_found(loan_id: uuid.UUID) -> Failure:
    return Failure(NotFoundError("PlateLoan", str(loan_id)))


# ---------------------------------------------------------------------------
# Use cases
# ---------------------------------------------------------------------------


class RequestPlateLoan:
    """Request a loan of one or more plates, resolved by id, barcode, or group."""

    def __init__(
        self,
        uow: UnitOfWork,
        loan_repo: PlateLoanRepository,
        plate_repo: RegisteredPlateRepository,
        group_repo: PlateGroupRepository,
        policy_repo: OrgPlatePolicyRepository,
        dispatcher: EventDispatcherProtocol,
        visibility: PlateVisibilityService,
    ) -> None:
        self._uow = uow
        self._loan_repo = loan_repo
        self._plate_repo = plate_repo
        self._group_repo = group_repo
        self._policy_repo = policy_repo
        self._dispatcher = dispatcher
        self._visibility = visibility

    async def __call__(
        self, input: RequestPlateLoanCommand, auth: AuthContext | None = None
    ) -> Result[PlateLoan, DomainError]:
        require_editor(auth)
        require_same_workspace(auth, input.workspace_id)

        borrower_org_id = auth.org_id if auth is not None else None
        if borrower_org_id is None:
            return Failure(ValidationError("Caller has no organization — loans require an org"))

        # Empty lists count as "not provided" — a mode with nothing in it
        # is the same as omitting it, and this sidesteps a would-be empty
        # resolved-plates set falling through to the wrong error below.
        has_plate_ids = bool(input.plate_ids)
        has_barcodes = bool(input.barcodes)
        has_group = input.group_id is not None
        if sum((has_plate_ids, has_barcodes, has_group)) != 1:
            return Failure(
                ValidationError("Exactly one of plate_ids, barcodes, or group_id must be provided")
            )

        async with self._uow:
            excluded = await self._visibility.excluded_org_ids(input.workspace_id, auth)

            if has_plate_ids:
                assert input.plate_ids is not None
                found_by_id = {
                    p.id: p
                    for p in await self._plate_repo.find_by_ids(
                        input.workspace_id, input.plate_ids
                    )
                }
                plates = []
                for plate_id in input.plate_ids:
                    plate = found_by_id.get(plate_id)
                    if plate is None or not self._visibility.can_view(plate, auth, excluded):
                        # Missing and hidden report identically — no
                        # existence oracle for plates outside the caller's org.
                        return Failure(NotFoundError("RegisteredPlate", str(plate_id)))
                    plates.append(plate)
            elif has_barcodes:
                assert input.barcodes is not None
                plates = []
                misses: list[str] = []
                for raw in input.barcodes:
                    plate = await resolve_barcode(self._plate_repo, input.workspace_id, raw)
                    if plate is None or not self._visibility.can_view(plate, auth, excluded):
                        misses.append(raw)
                        continue
                    plates.append(plate)
                if misses:
                    quoted = ", ".join(f"'{b}'" for b in misses)
                    return Failure(ValidationError(f"Unknown barcodes: {quoted}"))
            else:
                assert input.group_id is not None
                group = await self._group_repo.find_by_id_in_workspace(
                    input.workspace_id, input.group_id
                )
                if group is None or not self._visibility.can_view_owner(
                    group.owner_org_id, excluded
                ):
                    return Failure(NotFoundError("PlateGroup", str(input.group_id)))
                # Not filtered by `excluded` here: group visibility already
                # gated access above, and every plate assigned to a group
                # shares that group's owner org (S3 invariant, enforced in
                # AssignPlatesToGroup) — so the outcome is identical either way.
                plates = await self._plate_repo.search(input.workspace_id, group_id=group.id)
                if not plates:
                    return Failure(ValidationError("Group has no plates"))

            for plate in plates:
                if plate.owner_org_id is None:
                    return Failure(
                        ValidationError(
                            f"Plate '{plate.barcode.value}' has no owner organization "
                            "— set ownership before loaning"
                        )
                    )
            owner_org_ids = {p.owner_org_id for p in plates}
            if len(owner_org_ids) != 1:
                return Failure(ValidationError("Plates span multiple organizations"))
            owner_org_id = owner_org_ids.pop()

            active = await self._loan_repo.active_plate_ids(
                input.workspace_id, [p.id for p in plates]
            )
            if active:
                # Safe to name them: every plate here already passed the
                # caller's visibility check above.
                barcodes = ", ".join(f"'{p.barcode.value}'" for p in plates if p.id in active)
                return Failure(ConflictError(f"Plates already on an active loan: {barcodes}"))

            policy = await self._policy_repo.find_by_org(
                input.workspace_id, owner_org_id
            ) or OrgPlatePolicy.create_default(
                workspace_id=input.workspace_id, org_id=owner_org_id
            )

            if policy.default_due_days:
                due = input.due_date or (date.today() + timedelta(days=policy.default_due_days))
            else:
                due = input.due_date

            loan = PlateLoan.request(
                workspace_id=input.workspace_id,
                owner_org_id=owner_org_id,
                borrower_org_id=borrower_org_id,
                requested_by=input.requested_by,
                plate_ids=[p.id for p in plates],
                auto_approved=not policy.require_approval,
                due_date=due,
                notes=input.notes,
            )
            if not policy.require_approval and policy.confirmation == LoanConfirmationMode.NONE:
                # Full self-serve: no approval step and no separate
                # checkout confirmation, so items go straight to checked-out.
                loan.confirm_checkout(loan.eligible_item_ids(LoanItemStatus.CHECKED_OUT))

            await self._loan_repo.save(loan)
            events = await self._uow.commit()

        await self._dispatcher.dispatch_all(events)
        return Success(loan)


class ListLoans:
    """List loans visible to the caller, each paired with its plates (spec §8)."""

    def __init__(
        self,
        uow: UnitOfWork,
        loan_repo: PlateLoanRepository,
        plate_repo: RegisteredPlateRepository,
        visibility: PlateVisibilityService,
    ) -> None:
        self._uow = uow
        self._loan_repo = loan_repo
        self._plate_repo = plate_repo
        self._visibility = visibility

    async def __call__(
        self, input: ListLoansQuery, auth: AuthContext | None = None
    ) -> Result[list[LoanWithPlates], DomainError]:
        require_workspace_role(auth, "viewer")
        require_same_workspace(auth, input.workspace_id)
        async with self._uow:
            excluded = await self._visibility.excluded_org_ids(input.workspace_id, auth)
            loans = await self._loan_repo.find_by_workspace(
                input.workspace_id,
                status=input.status,
                owner_org_id=input.owner_org_id,
                borrower_org_id=input.borrower_org_id,
                requested_by=input.requested_by,
                plate_id=input.plate_id,
                overdue=input.overdue,
            )
            visible = [loan for loan in loans if _loan_visible(loan, auth, excluded)]

            plate_ids = {item.plate_id for loan in visible for item in loan.items}
            plates = await self._plate_repo.find_by_ids(input.workspace_id, list(plate_ids))
            plates_by_id = {p.id: p for p in plates}

            return Success([LoanWithPlates(loan=loan, plates=plates_by_id) for loan in visible])


class GetLoan:
    """Retrieve a single loan with its plates, applying loan visibility (spec §8)."""

    def __init__(
        self,
        uow: UnitOfWork,
        loan_repo: PlateLoanRepository,
        plate_repo: RegisteredPlateRepository,
        visibility: PlateVisibilityService,
    ) -> None:
        self._uow = uow
        self._loan_repo = loan_repo
        self._plate_repo = plate_repo
        self._visibility = visibility

    async def __call__(
        self, input: GetLoanQuery, auth: AuthContext | None = None
    ) -> Result[LoanWithPlates, DomainError]:
        require_workspace_role(auth, "viewer")
        require_same_workspace(auth, input.workspace_id)
        async with self._uow:
            loan = await self._loan_repo.find_by_id_in_workspace(input.workspace_id, input.loan_id)
            if loan is None:
                return _loan_not_found(input.loan_id)
            excluded = await self._visibility.excluded_org_ids(input.workspace_id, auth)
            if not _loan_visible(loan, auth, excluded):
                # Hidden == missing — no existence leak across orgs.
                return _loan_not_found(input.loan_id)

            plate_ids = [item.plate_id for item in loan.items]
            plates = await self._plate_repo.find_by_ids(input.workspace_id, plate_ids)
            return Success(LoanWithPlates(loan=loan, plates={p.id: p for p in plates}))
