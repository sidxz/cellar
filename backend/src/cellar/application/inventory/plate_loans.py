"""PlateLoan use cases — request a loan (spec §7), list/get with loan visibility (spec §8),
and the six item-transition verbs: approve, deny, confirm-checkout, request-return,
confirm-return, cancel (state machine + policy collapse rules in spec §4.3).
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, timedelta

from returns.result import Failure, Result, Success

from cellar.application.auth import (
    AuthContext,
    require_authenticated,
    require_editor,
    require_loan_authority,
    require_same_workspace,
    require_workspace_role,
)
from cellar.application.inventory.barcode_resolution import resolve_barcode
from cellar.application.inventory.plate_visibility import PlateVisibilityService
from cellar.application.shared.command import Command
from cellar.application.shared.event_dispatcher import EventDispatcherProtocol
from cellar.application.shared.org_directory import OrgDirectoryPort
from cellar.application.shared.query import Query
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.inventory.comment import Comment
from cellar.domain.inventory.enums import CommentTarget, LoanConfirmationMode, LoanItemStatus
from cellar.domain.inventory.org_plate_policy import OrgPlatePolicy
from cellar.domain.inventory.plate_group import PlateGroup
from cellar.domain.inventory.plate_loan import LoanItem, PlateLoan
from cellar.domain.inventory.registered_plate import RegisteredPlate
from cellar.domain.inventory.repository import (
    CommentRepository,
    OrgPlatePolicyRepository,
    PlateGroupRepository,
    PlateLoanRepository,
    RegisteredPlateRepository,
)
from cellar.domain.shared.errors import (
    AuthorizationError,
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
    borrower_org_id: uuid.UUID | None = None
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
    groups: dict[uuid.UUID, PlateGroup] = field(default_factory=dict)


async def enrich_loans(
    loans: list[PlateLoan],
    *,
    plate_repo: RegisteredPlateRepository,
    group_repo: PlateGroupRepository,
) -> list[LoanWithPlates]:
    """One plate fetch + one group fetch for any number of loans (no N+1)."""
    if not loans:
        return []
    ws = loans[0].workspace_id
    plate_ids = sorted({i.plate_id for loan in loans for i in loan.items})
    plates = {p.id: p for p in await plate_repo.find_by_ids(ws, plate_ids)}
    group_ids = sorted({p.group_id for p in plates.values() if p.group_id is not None})
    groups = {g.id: g for g in await group_repo.find_by_ids(ws, group_ids)}
    out: list[LoanWithPlates] = []
    for loan in loans:
        mine = {i.plate_id: plates[i.plate_id] for i in loan.items if i.plate_id in plates}
        mine_group_ids = {p.group_id for p in mine.values() if p.group_id}
        loan_groups = {gid: groups[gid] for gid in mine_group_ids if gid in groups}
        out.append(LoanWithPlates(loan=loan, plates=mine, groups=loan_groups))
    return out


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
        org_directory: OrgDirectoryPort,
    ) -> None:
        self._uow = uow
        self._loan_repo = loan_repo
        self._plate_repo = plate_repo
        self._group_repo = group_repo
        self._policy_repo = policy_repo
        self._dispatcher = dispatcher
        self._visibility = visibility
        self._org_directory = org_directory

    async def __call__(
        self, input: RequestPlateLoanCommand, auth: AuthContext | None = None
    ) -> Result[PlateLoan, DomainError]:
        require_editor(auth)
        require_same_workspace(auth, input.workspace_id)

        caller_org_id = auth.org_id if auth is not None else None
        if caller_org_id is None:
            return Failure(ValidationError("Caller has no organization — loans require an org"))
        borrower_org_id = input.borrower_org_id or caller_org_id
        owner_initiated = borrower_org_id != caller_org_id

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
                # Direct members only, by design (user ruling 2026-08-26): a
                # loan is of a SET — people request the group that holds the
                # plates, never a library whose plates live in child sets. The
                # UI offers "Request loan" only where plate_count > 0.
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

            if owner_initiated:
                # Ruling R6 (+ 2026-08-26): a lend is the owner org APPROVING its
                # own loan on creation, so it must clear exactly the approve
                # verb's authority — admin, or an owner-org editor holding
                # cellar:approve_loan. Anything weaker lets any editor pick a
                # foreign borrower org and walk out with plates unapproved.
                # Foreign plates are already hidden → 404 above.
                await require_loan_authority(auth, owner_org_id)
                known = {o.id for o in await self._org_directory.list_orgs()}
                if borrower_org_id not in known:
                    return Failure(ValidationError("Unknown borrower organization"))

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
                auto_approved=not policy.require_approval and not owner_initiated,
                due_date=due,
                notes=input.notes,
            )
            if owner_initiated:
                # The owner is lending: it approves its own loan on creation.
                loan.approve_items(
                    loan.eligible_item_ids(LoanItemStatus.APPROVED), approved_by=input.requested_by
                )
            if policy.confirmation == LoanConfirmationMode.NONE and (
                owner_initiated or not policy.require_approval
            ):
                # No separate checkout confirmation step, so approved items
                # go straight to checked-out (self-serve and owner-lend alike).
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
        group_repo: PlateGroupRepository,
    ) -> None:
        self._uow = uow
        self._loan_repo = loan_repo
        self._plate_repo = plate_repo
        self._visibility = visibility
        self._group_repo = group_repo

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

            return Success(
                await enrich_loans(
                    visible, plate_repo=self._plate_repo, group_repo=self._group_repo
                )
            )


class GetLoan:
    """Retrieve a single loan with its plates, applying loan visibility (spec §8)."""

    def __init__(
        self,
        uow: UnitOfWork,
        loan_repo: PlateLoanRepository,
        plate_repo: RegisteredPlateRepository,
        visibility: PlateVisibilityService,
        group_repo: PlateGroupRepository,
    ) -> None:
        self._uow = uow
        self._loan_repo = loan_repo
        self._plate_repo = plate_repo
        self._visibility = visibility
        self._group_repo = group_repo

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

            result = await enrich_loans(
                [loan], plate_repo=self._plate_repo, group_repo=self._group_repo
            )
            return Success(result[0])


# ---------------------------------------------------------------------------
# Item-transition command + use cases (approve/deny/confirm-out/return/cancel)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, kw_only=True)
class LoanItemsCommand(Command):
    workspace_id: uuid.UUID
    loan_id: uuid.UUID
    item_ids: list[uuid.UUID] | None = None  # None = every item eligible for the verb's target


@dataclass(frozen=True)
class GroupComment:
    group_id: uuid.UUID
    body: str


@dataclass(frozen=True)
class PlateComment:
    plate_id: uuid.UUID
    body: str


@dataclass(frozen=True, kw_only=True)
class RequestLoanReturnCommand(LoanItemsCommand):
    comments: tuple[GroupComment, ...] = ()
    plate_comments: tuple[PlateComment, ...] = ()


async def _require_borrower_authority(auth: AuthContext | None, loan: PlateLoan) -> None:
    """Borrower-side loan verbs (request-return/cancel): admin or the borrower
    org itself. Mirrors ``require_loan_authority``'s ordering discipline —
    require_authenticated then require_editor before any auth field is read."""
    require_authenticated(auth)
    require_editor(auth)
    assert auth is not None  # require_authenticated raised otherwise
    if auth.is_admin or auth.org_id == loan.borrower_org_id:
        return
    raise AuthorizationError("Only the borrower organization can manage this loan")


class _LoanItemsUseCase:
    """Shared machinery for the six item-transition verbs: load loan
    (hidden==missing), authorize, expand ``item_ids=None`` to all-eligible
    for the verb's target status, apply the verb, run policy collapse, save,
    and enrich with plates (``GetLoan``'s per-loan ``find_by_ids`` shape)."""

    _target: LoanItemStatus  # subclass sets

    def __init__(
        self,
        uow: UnitOfWork,
        repo: PlateLoanRepository,
        plate_repo: RegisteredPlateRepository,
        policy_repo: OrgPlatePolicyRepository,
        dispatcher: EventDispatcherProtocol,
        visibility: PlateVisibilityService,
        group_repo: PlateGroupRepository,
    ) -> None:
        self._uow = uow
        self._repo = repo
        self._plate_repo = plate_repo
        self._policy_repo = policy_repo
        self._dispatcher = dispatcher
        self._visibility = visibility
        self._group_repo = group_repo

    async def __call__(
        self, input: LoanItemsCommand, auth: AuthContext | None = None
    ) -> Result[LoanWithPlates, DomainError]:
        require_editor(auth)
        require_same_workspace(auth, input.workspace_id)
        async with self._uow:
            loan = await self._repo.find_by_id_in_workspace(input.workspace_id, input.loan_id)
            if loan is None:
                return _loan_not_found(input.loan_id)
            excluded = await self._visibility.excluded_org_ids(input.workspace_id, auth)
            if not _loan_visible(loan, auth, excluded):
                # Hidden == missing — no existence leak across orgs, and this
                # 404 must win over a 403 for a caller with no authority at
                # all on an otherwise-invisible loan.
                return _loan_not_found(input.loan_id)

            await self._authorize(auth, loan)

            item_ids = (
                input.item_ids
                if input.item_ids is not None
                else loan.eligible_item_ids(self._target)
            )
            if not item_ids:
                return Failure(ValidationError("No eligible loan items"))

            err = await self._validate(loan, item_ids, input, auth)
            if err is not None:
                return Failure(err)

            self._apply(loan, item_ids, auth)
            await self._collapse(loan, item_ids)

            await self._repo.save(loan)
            await self._after_save(loan, item_ids, input, auth)
            events = await self._uow.commit()
            # Enrich INSIDE the block — the UoW session closes on exit; a
            # post-block repo call raises RuntimeError. Post-commit reads on
            # the still-open session are fine.
            result = await self._enrich(loan)

        await self._dispatcher.dispatch_all(events)
        return Success(result)

    # -- hooks (subclasses set these) ------------------------------------

    async def _authorize(self, auth: AuthContext | None, loan: PlateLoan) -> None:
        raise NotImplementedError

    def _apply(self, loan: PlateLoan, item_ids: list[uuid.UUID], auth: AuthContext | None) -> None:
        raise NotImplementedError

    async def _collapse(self, loan: PlateLoan, item_ids: list[uuid.UUID]) -> None:
        return None  # most verbs don't auto-collapse into the next status

    async def _validate(
        self,
        loan: PlateLoan,
        item_ids: list[uuid.UUID],
        input: LoanItemsCommand,
        auth: AuthContext | None,
    ) -> DomainError | None:
        return None  # most verbs need no extra pre-condition beyond the state machine

    async def _after_save(
        self,
        loan: PlateLoan,
        item_ids: list[uuid.UUID],
        input: LoanItemsCommand,
        auth: AuthContext | None,
    ) -> None:
        return None  # most verbs have no side effect beyond the item transition

    # -- shared helpers ----------------------------------------------------

    async def _policy_collapse(
        self,
        loan: PlateLoan,
        item_ids: list[uuid.UUID],
        target: LoanItemStatus,
        verb: Callable[[list[uuid.UUID]], list[LoanItem]],
    ) -> None:
        """Approve/RequestReturn collapse: when the owner org's policy has no
        separate confirmation step, immediately advance the just-processed
        items to *target* too — expanded via ``eligible_item_ids(target)``,
        intersected (order-preserving) with the items this call processed."""
        policy = await self._policy_repo.find_by_org(
            loan.workspace_id, loan.owner_org_id
        ) or OrgPlatePolicy.create_default(
            workspace_id=loan.workspace_id, org_id=loan.owner_org_id
        )
        if policy.confirmation != LoanConfirmationMode.NONE:
            return
        eligible = set(loan.eligible_item_ids(target))
        expanded = [i for i in item_ids if i in eligible]
        if expanded:
            verb(expanded)

    async def _enrich(self, loan: PlateLoan) -> LoanWithPlates:
        result = await enrich_loans(
            [loan], plate_repo=self._plate_repo, group_repo=self._group_repo
        )
        return result[0]


class ApproveLoanItems(_LoanItemsUseCase):
    """Owner approves items still in REQUESTED."""

    _target = LoanItemStatus.APPROVED

    async def _authorize(self, auth: AuthContext | None, loan: PlateLoan) -> None:
        await require_loan_authority(auth, loan.owner_org_id)

    def _apply(self, loan: PlateLoan, item_ids: list[uuid.UUID], auth: AuthContext | None) -> None:
        assert auth is not None  # require_loan_authority raised otherwise
        loan.approve_items(item_ids, approved_by=auth.user_id)

    async def _collapse(self, loan: PlateLoan, item_ids: list[uuid.UUID]) -> None:
        await self._policy_collapse(
            loan, item_ids, LoanItemStatus.CHECKED_OUT, loan.confirm_checkout
        )


class DenyLoanItems(_LoanItemsUseCase):
    """Owner denies items still in REQUESTED."""

    _target = LoanItemStatus.DENIED

    async def _authorize(self, auth: AuthContext | None, loan: PlateLoan) -> None:
        await require_loan_authority(auth, loan.owner_org_id)

    def _apply(self, loan: PlateLoan, item_ids: list[uuid.UUID], auth: AuthContext | None) -> None:
        loan.deny_items(item_ids)


class ConfirmLoanCheckout(_LoanItemsUseCase):
    """Owner confirms physical handoff of APPROVED items to the borrower."""

    _target = LoanItemStatus.CHECKED_OUT

    async def _authorize(self, auth: AuthContext | None, loan: PlateLoan) -> None:
        await require_loan_authority(auth, loan.owner_org_id)

    def _apply(self, loan: PlateLoan, item_ids: list[uuid.UUID], auth: AuthContext | None) -> None:
        loan.confirm_checkout(item_ids)


class RequestLoanReturn(_LoanItemsUseCase):
    """Borrower requests to return CHECKED_OUT items.

    Spec §7.3: the legacy tracker demanded one comment per set describing
    what was done with those plates at check-in — reproduced here as one
    non-empty comment per distinct group among the *returning* items.
    """

    _target = LoanItemStatus.RETURN_PENDING

    def __init__(
        self,
        uow: UnitOfWork,
        repo: PlateLoanRepository,
        plate_repo: RegisteredPlateRepository,
        policy_repo: OrgPlatePolicyRepository,
        dispatcher: EventDispatcherProtocol,
        visibility: PlateVisibilityService,
        group_repo: PlateGroupRepository,
        comment_repo: CommentRepository,
    ) -> None:
        super().__init__(uow, repo, plate_repo, policy_repo, dispatcher, visibility, group_repo)
        self._comment_repo = comment_repo

    async def _authorize(self, auth: AuthContext | None, loan: PlateLoan) -> None:
        await _require_borrower_authority(auth, loan)

    def _apply(self, loan: PlateLoan, item_ids: list[uuid.UUID], auth: AuthContext | None) -> None:
        loan.request_return(item_ids)

    async def _collapse(self, loan: PlateLoan, item_ids: list[uuid.UUID]) -> None:
        await self._policy_collapse(loan, item_ids, LoanItemStatus.RETURNED, loan.confirm_return)

    async def _validate(
        self,
        loan: PlateLoan,
        item_ids: list[uuid.UUID],
        input: LoanItemsCommand,
        auth: AuthContext | None,
    ) -> DomainError | None:
        if not isinstance(input, RequestLoanReturnCommand):
            return None
        returning = {i.plate_id for i in loan.items if i.id in set(item_ids)}
        plates = await self._plate_repo.find_by_ids(loan.workspace_id, sorted(returning))
        required = {p.group_id for p in plates if p.group_id is not None}
        provided_ids = {c.group_id for c in input.comments}
        extra = provided_ids - required
        if extra:
            return ValidationError("comments may only name groups of the plates being returned")
        provided = {c.group_id for c in input.comments if c.body.strip()}
        missing = required - provided
        if missing:
            groups = await self._group_repo.find_by_ids(loan.workspace_id, sorted(missing))
            names = ", ".join(sorted(g.name for g in groups)) or ", ".join(
                str(m) for m in sorted(missing)
            )
            return ValidationError(f"A return comment is required for group(s): {names}")
        for pc in input.plate_comments:
            if pc.plate_id not in returning:
                return ValidationError("plate_comments may only name plates being returned")
        return None

    async def _after_save(
        self,
        loan: PlateLoan,
        item_ids: list[uuid.UUID],
        input: LoanItemsCommand,
        auth: AuthContext | None,
    ) -> None:
        if not isinstance(input, RequestLoanReturnCommand) or auth is None:
            return
        author = auth.name or auth.email
        for gc in input.comments:
            if gc.body.strip():
                await self._comment_repo.save(
                    Comment.create(
                        workspace_id=loan.workspace_id,
                        target_type=CommentTarget.PLATE_GROUP,
                        target_id=gc.group_id,
                        body=gc.body,
                        author_id=auth.user_id,
                        author_name=author,
                        loan_id=loan.id,
                    )
                )
        for pc in input.plate_comments:
            if pc.body.strip():
                await self._comment_repo.save(
                    Comment.create(
                        workspace_id=loan.workspace_id,
                        target_type=CommentTarget.PLATE,
                        target_id=pc.plate_id,
                        body=pc.body,
                        author_id=auth.user_id,
                        author_name=author,
                        loan_id=loan.id,
                    )
                )


class ConfirmLoanReturn(_LoanItemsUseCase):
    """Owner confirms physical handoff of RETURN_PENDING items back."""

    _target = LoanItemStatus.RETURNED

    async def _authorize(self, auth: AuthContext | None, loan: PlateLoan) -> None:
        await require_loan_authority(auth, loan.owner_org_id)

    def _apply(self, loan: PlateLoan, item_ids: list[uuid.UUID], auth: AuthContext | None) -> None:
        loan.confirm_return(item_ids)


class CancelLoanItems(_LoanItemsUseCase):
    """Borrower cancels items still REQUESTED or APPROVED (not yet checked out).

    Ruling R7 (final review I3): the owner org may retract items it hasn't
    handed over yet too — a mis-lend (wrong borrower_org_id on an
    owner-initiated loan, ruling R6) needs an undo verb, and the owner
    already has the authority to *approve* those same items. Try borrower
    authority first (the common case); on failure, fall back to owner loan
    authority (admin bypass, org match, cellar:approve_loan) rather than
    granting both unconditionally, so an unrelated org still gets a single
    clean 403.
    """

    _target = LoanItemStatus.CANCELLED

    async def _authorize(self, auth: AuthContext | None, loan: PlateLoan) -> None:
        try:
            await _require_borrower_authority(auth, loan)
        except AuthorizationError:
            await require_loan_authority(auth, loan.owner_org_id)

    def _apply(self, loan: PlateLoan, item_ids: list[uuid.UUID], auth: AuthContext | None) -> None:
        loan.cancel_items(item_ids)
