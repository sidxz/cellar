"""PlateLoan API routes — request, item-transition verbs, filters, loan visibility."""

from __future__ import annotations

import uuid
from datetime import date, datetime

from fastapi import APIRouter
from pydantic import BaseModel

from cellar.application.inventory.plate_loans import (
    GetLoanQuery,
    GroupComment,
    ListLoansQuery,
    LoanItemsCommand,
    LoanWithPlates,
    PlateComment,
    RequestLoanReturnCommand,
    RequestPlateLoanCommand,
)
from cellar.application.inventory.shipment_reads import ListShipmentsForLoanQuery
from cellar.domain.inventory.enums import LoanItemStatus, LoanStatus
from cellar.interface.dependencies import (
    ApproveLoanItemsDep,
    AuthDep,
    CancelLoanItemsDep,
    ConfirmLoanCheckoutDep,
    ConfirmLoanReturnDep,
    DenyLoanItemsDep,
    GetLoanDep,
    ListLoansDep,
    ListShipmentsForLoanDep,
    RequestLoanReturnDep,
    RequestPlateLoanDep,
)
from cellar.interface.error_handlers import result_to_response
from cellar.interface.routes.shipments import ShipmentLinkResponse

router = APIRouter(prefix="/api/v1/plate-loans", tags=["plate-loans"])


# ---------------------------------------------------------------------------
# Response / request models
# ---------------------------------------------------------------------------


class LoanItemResponse(BaseModel):
    id: uuid.UUID
    plate_id: uuid.UUID
    barcode: str
    plate_label: str
    status: LoanItemStatus
    status_changed_at: datetime
    group_id: uuid.UUID | None = None
    group_name: str | None = None


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
    def from_dto(cls, dto: LoanWithPlates) -> LoanResponse:
        """Map items via ``dto.plates`` — a map SHARED across every loan a
        given ``ListLoans`` call returns (Task 5 reviewer flag: not scoped to
        this loan alone), so items are looked up by ``item.plate_id`` rather
        than assuming the dict only holds this loan's plates. A plate absent
        from the map (deleted after the loan closed) falls back to
        placeholders instead of failing the response."""
        loan = dto.loan
        items = []
        for item in loan.items:
            plate = dto.plates.get(item.plate_id)
            group = (
                dto.groups.get(plate.group_id) if plate is not None and plate.group_id else None
            )
            items.append(
                LoanItemResponse(
                    id=item.id,
                    plate_id=item.plate_id,
                    barcode=plate.barcode.value if plate is not None else "(deleted plate)",
                    plate_label=plate.plate_label if plate is not None else "",
                    status=item.status,
                    status_changed_at=item.status_changed_at,
                    group_id=group.id if group is not None else None,
                    group_name=group.name if group is not None else None,
                )
            )
        return cls(
            id=loan.id,
            workspace_id=loan.workspace_id,
            owner_org_id=loan.owner_org_id,
            borrower_org_id=loan.borrower_org_id,
            requested_by=loan.requested_by,
            approved_by=loan.approved_by,
            due_date=loan.due_date,
            notes=loan.notes,
            status=loan.status,
            closed_at=loan.closed_at,
            created_at=loan.created_at,
            items=items,
            version=loan.version,
        )


class RequestLoanBody(BaseModel):
    plate_ids: list[uuid.UUID] | None = None
    barcodes: list[str] | None = None
    group_id: uuid.UUID | None = None
    borrower_org_id: uuid.UUID | None = None
    due_date: date | None = None
    notes: str | None = None

    model_config = {"extra": "forbid"}


class LoanItemsBody(BaseModel):
    item_ids: list[uuid.UUID] | None = None

    model_config = {"extra": "forbid"}


class GroupCommentBody(BaseModel):
    group_id: uuid.UUID
    body: str

    model_config = {"extra": "forbid"}


class PlateCommentBody(BaseModel):
    plate_id: uuid.UUID
    body: str

    model_config = {"extra": "forbid"}


class RequestReturnBody(LoanItemsBody):
    comments: list[GroupCommentBody] = []
    plate_comments: list[PlateCommentBody] = []


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("", response_model=LoanResponse, status_code=201)
async def request_plate_loan(
    body: RequestLoanBody,
    auth: AuthDep,
    uc: RequestPlateLoanDep,
    get_uc: GetLoanDep,
) -> LoanResponse:
    """Request a loan of one or more plates (by id, barcode, or group)."""
    command = RequestPlateLoanCommand(
        workspace_id=auth.workspace_id,
        requested_by=auth.user_id,
        plate_ids=body.plate_ids,
        barcodes=body.barcodes,
        group_id=body.group_id,
        borrower_org_id=body.borrower_org_id,
        due_date=body.due_date,
        notes=body.notes,
    )
    loan = result_to_response(await uc(command, auth=auth))
    # RequestPlateLoan returns the bare aggregate (no plate enrichment) — a
    # second, already-exported use case (GetLoan) re-fetches it enriched, the
    # same "create, then compose a read use case for the response" idiom as
    # runs.py::create_run + ResolveRunTargetsDep.
    dto = result_to_response(
        await get_uc(GetLoanQuery(workspace_id=auth.workspace_id, loan_id=loan.id), auth=auth)
    )
    return LoanResponse.from_dto(dto)


@router.get("", response_model=list[LoanResponse])
async def list_loans(
    auth: AuthDep,
    uc: ListLoansDep,
    status: LoanStatus | None = None,
    owner_org_id: uuid.UUID | None = None,
    borrower_org_id: uuid.UUID | None = None,
    mine: bool = False,
    plate_id: uuid.UUID | None = None,
    overdue: bool = False,
) -> list[LoanResponse]:
    """List loans visible to the caller, with optional filters."""
    query = ListLoansQuery(
        workspace_id=auth.workspace_id,
        status=status.value if status is not None else None,
        owner_org_id=owner_org_id,
        borrower_org_id=borrower_org_id,
        requested_by=auth.user_id if mine else None,
        plate_id=plate_id,
        overdue=overdue,
    )
    loans = result_to_response(await uc(query, auth=auth))
    return [LoanResponse.from_dto(dto) for dto in loans]


@router.get("/{loan_id}", response_model=LoanResponse)
async def get_loan(loan_id: uuid.UUID, auth: AuthDep, uc: GetLoanDep) -> LoanResponse:
    """Retrieve a single loan with its plates."""
    query = GetLoanQuery(workspace_id=auth.workspace_id, loan_id=loan_id)
    dto = result_to_response(await uc(query, auth=auth))
    return LoanResponse.from_dto(dto)


@router.get("/{loan_id}/shipments", response_model=list[ShipmentLinkResponse])
async def list_loan_shipments(
    loan_id: uuid.UUID, auth: AuthDep, uc: ListShipmentsForLoanDep
) -> list[ShipmentLinkResponse]:
    """Shipments carrying this loan's plates (lend or return leg), newest first.

    Same loan visibility as GET /{loan_id} — a hidden loan 404s like a missing one.
    """
    query = ListShipmentsForLoanQuery(workspace_id=auth.workspace_id, loan_id=loan_id)
    rows = result_to_response(await uc(query, auth=auth))
    return [ShipmentLinkResponse.from_row(r) for r in rows]


@router.post("/{loan_id}/items:approve", response_model=LoanResponse)
async def approve_loan_items(
    loan_id: uuid.UUID, body: LoanItemsBody, auth: AuthDep, uc: ApproveLoanItemsDep
) -> LoanResponse:
    """Owner approves items still REQUESTED (item_ids=None = all eligible)."""
    command = LoanItemsCommand(
        workspace_id=auth.workspace_id, loan_id=loan_id, item_ids=body.item_ids
    )
    dto = result_to_response(await uc(command, auth=auth))
    return LoanResponse.from_dto(dto)


@router.post("/{loan_id}/items:deny", response_model=LoanResponse)
async def deny_loan_items(
    loan_id: uuid.UUID, body: LoanItemsBody, auth: AuthDep, uc: DenyLoanItemsDep
) -> LoanResponse:
    """Owner denies items still REQUESTED."""
    command = LoanItemsCommand(
        workspace_id=auth.workspace_id, loan_id=loan_id, item_ids=body.item_ids
    )
    dto = result_to_response(await uc(command, auth=auth))
    return LoanResponse.from_dto(dto)


@router.post("/{loan_id}/items:confirm-out", response_model=LoanResponse)
async def confirm_loan_checkout(
    loan_id: uuid.UUID, body: LoanItemsBody, auth: AuthDep, uc: ConfirmLoanCheckoutDep
) -> LoanResponse:
    """Owner confirms physical handoff of APPROVED items to the borrower."""
    command = LoanItemsCommand(
        workspace_id=auth.workspace_id, loan_id=loan_id, item_ids=body.item_ids
    )
    dto = result_to_response(await uc(command, auth=auth))
    return LoanResponse.from_dto(dto)


@router.post("/{loan_id}/items:request-return", response_model=LoanResponse)
async def request_loan_return(
    loan_id: uuid.UUID, body: RequestReturnBody, auth: AuthDep, uc: RequestLoanReturnDep
) -> LoanResponse:
    """Borrower requests to return CHECKED_OUT items. Spec §7.3: one non-empty
    comment is required per distinct group among the returning plates."""
    command = RequestLoanReturnCommand(
        workspace_id=auth.workspace_id,
        loan_id=loan_id,
        item_ids=body.item_ids,
        comments=tuple(GroupComment(c.group_id, c.body) for c in body.comments),
        plate_comments=tuple(PlateComment(p.plate_id, p.body) for p in body.plate_comments),
    )
    dto = result_to_response(await uc(command, auth=auth))
    return LoanResponse.from_dto(dto)


@router.post("/{loan_id}/items:confirm-in", response_model=LoanResponse)
async def confirm_loan_return(
    loan_id: uuid.UUID, body: LoanItemsBody, auth: AuthDep, uc: ConfirmLoanReturnDep
) -> LoanResponse:
    """Owner confirms physical handoff of RETURN_PENDING items back."""
    command = LoanItemsCommand(
        workspace_id=auth.workspace_id, loan_id=loan_id, item_ids=body.item_ids
    )
    dto = result_to_response(await uc(command, auth=auth))
    return LoanResponse.from_dto(dto)


@router.post("/{loan_id}/items:cancel", response_model=LoanResponse)
async def cancel_loan_items(
    loan_id: uuid.UUID, body: LoanItemsBody, auth: AuthDep, uc: CancelLoanItemsDep
) -> LoanResponse:
    """Borrower cancels items still REQUESTED or APPROVED (not yet checked out)."""
    command = LoanItemsCommand(
        workspace_id=auth.workspace_id, loan_id=loan_id, item_ids=body.item_ids
    )
    dto = result_to_response(await uc(command, auth=auth))
    return LoanResponse.from_dto(dto)
