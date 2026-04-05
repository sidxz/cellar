"""SynthesisRequest API routes."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from chem_vault.application.inventory.synthesis_requests import (
    ApproveSynthesisRequest,
    ApproveSynthesisRequestCommand,
    AssignSynthesisRequest,
    AssignSynthesisRequestCommand,
    CancelSynthesisRequest,
    CancelSynthesisRequestCommand,
    CompleteSynthesis,
    CompleteSynthesisCommand,
    CreateSynthesisRequest,
    CreateSynthesisRequestCommand,
    DeleteSynthesisRequest,
    DeleteSynthesisRequestCommand,
    FailSynthesis,
    FailSynthesisCommand,
    FlagInfeasible,
    FlagInfeasibleCommand,
    FulfillSynthesisRequest,
    FulfillSynthesisRequestCommand,
    GetSynthesisRequest,
    GetSynthesisRequestQuery,
    ListSynthesisRequests,
    ListSynthesisRequestsQuery,
    RejectSynthesisRequest,
    RejectSynthesisRequestCommand,
    StartSynthesis,
    StartSynthesisCommand,
    SubmitSynthesisRequest,
    SubmitSynthesisRequestCommand,
    UpdateSynthesisRequest,
    UpdateSynthesisRequestCommand,
)
from chem_vault.interface.dependencies import AuthDep, _get_use_case
from chem_vault.interface.error_handlers import result_to_response

router = APIRouter(prefix="/api/v1", tags=["synthesis-requests"])


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class SynthesisRequestResponse(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    requester_id: uuid.UUID
    molecule_id: uuid.UUID
    amount_value: float
    amount_unit: str
    purpose: str
    priority: str
    status: str
    target_purity: float | None = None
    project_id: uuid.UUID | None = None
    approved_by: uuid.UUID | None = None
    approved_at: str | None = None
    rejection_reason: str | None = None
    assignment_type: str | None = None
    assigned_to: uuid.UUID | None = None
    assigned_org_id: uuid.UUID | None = None
    proposed_route_id: uuid.UUID | None = None
    feasibility_status: str | None = None
    feasibility_notes: str | None = None
    estimated_cost_value: float | None = None
    estimated_cost_unit: str | None = None
    actual_cost_value: float | None = None
    actual_cost_unit: str | None = None
    estimated_completion_date: str | None = None
    actual_completion_date: str | None = None
    fulfilled_batch_id: uuid.UUID | None = None
    failure_reason: str | None = None
    parent_request_id: uuid.UUID | None = None

    @classmethod
    def from_domain(cls, r) -> SynthesisRequestResponse:  # type: ignore[no-untyped-def]
        return cls(
            id=r.id,
            workspace_id=r.workspace_id,
            requester_id=r.requester_id,
            molecule_id=r.molecule_id,
            amount_value=r.requested_amount.value,
            amount_unit=r.requested_amount.unit.value,
            purpose=r.purpose,
            priority=r.priority.value,
            status=r.status.value,
            target_purity=r.target_purity,
            project_id=r.project_id,
            approved_by=r.approved_by,
            approved_at=r.approved_at.isoformat() if r.approved_at else None,
            rejection_reason=r.rejection_reason,
            assignment_type=r.assignment.assignment_type.value if r.assignment else None,
            assigned_to=r.assignment.assigned_to if r.assignment else None,
            assigned_org_id=r.assignment.assigned_org_id if r.assignment else None,
            proposed_route_id=r.proposed_route_id,
            feasibility_status=r.feasibility_status.value if r.feasibility_status else None,
            feasibility_notes=r.feasibility_notes,
            estimated_cost_value=r.estimated_cost.value if r.estimated_cost else None,
            estimated_cost_unit=r.estimated_cost.unit.value if r.estimated_cost else None,
            actual_cost_value=r.actual_cost.value if r.actual_cost else None,
            actual_cost_unit=r.actual_cost.unit.value if r.actual_cost else None,
            estimated_completion_date=(
                r.estimated_completion_date.isoformat() if r.estimated_completion_date else None
            ),
            actual_completion_date=(
                r.actual_completion_date.isoformat() if r.actual_completion_date else None
            ),
            fulfilled_batch_id=r.fulfilled_batch_id,
            failure_reason=r.failure_reason,
            parent_request_id=r.parent_request_id,
        )


class SynthesisRequestSummaryResponse(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    requester_id: uuid.UUID
    molecule_id: uuid.UUID
    amount_value: float
    amount_unit: str
    purpose: str
    priority: str
    status: str
    target_purity: float | None = None

    @classmethod
    def from_domain(cls, r) -> SynthesisRequestSummaryResponse:  # type: ignore[no-untyped-def]
        return cls(
            id=r.id,
            workspace_id=r.workspace_id,
            requester_id=r.requester_id,
            molecule_id=r.molecule_id,
            amount_value=r.requested_amount.value,
            amount_unit=r.requested_amount.unit.value,
            purpose=r.purpose,
            priority=r.priority.value,
            status=r.status.value,
            target_purity=r.target_purity,
        )


# ---------------------------------------------------------------------------
# Request bodies
# ---------------------------------------------------------------------------


class CreateSynthesisRequestRequest(BaseModel):
    molecule_id: uuid.UUID
    amount_value: float
    amount_unit: str
    purpose: str
    priority: str = "routine"
    target_purity: float | None = None
    project_id: uuid.UUID | None = None
    parent_request_id: uuid.UUID | None = None


class RejectRequest(BaseModel):
    reason: str


class AssignRequest(BaseModel):
    assignment_type: str
    assigned_to: uuid.UUID | None = None
    assigned_org_id: uuid.UUID | None = None


class StartRequest(BaseModel):
    proposed_route_id: uuid.UUID | None = None


class FlagInfeasibleRequest(BaseModel):
    feasibility_status: str
    feasibility_notes: str | None = None


class CompleteRequest(BaseModel):
    actual_cost_value: float | None = None
    actual_cost_unit: str | None = None


class FulfillRequest(BaseModel):
    batch_id: uuid.UUID


class FailRequest(BaseModel):
    reason: str


class UpdateSynthesisRequestRequest(BaseModel):
    purpose: str | None = None
    priority: str | None = None
    amount_value: float | None = None
    amount_unit: str | None = None
    target_purity: float | None = None


# ---------------------------------------------------------------------------
# Dependencies
# ---------------------------------------------------------------------------


CreateSynthesisRequestDep = Annotated[CreateSynthesisRequest, Depends(_get_use_case(CreateSynthesisRequest))]
SubmitSynthesisRequestDep = Annotated[SubmitSynthesisRequest, Depends(_get_use_case(SubmitSynthesisRequest))]
ApproveSynthesisRequestDep = Annotated[ApproveSynthesisRequest, Depends(_get_use_case(ApproveSynthesisRequest))]
RejectSynthesisRequestDep = Annotated[RejectSynthesisRequest, Depends(_get_use_case(RejectSynthesisRequest))]
AssignSynthesisRequestDep = Annotated[AssignSynthesisRequest, Depends(_get_use_case(AssignSynthesisRequest))]
StartSynthesisDep = Annotated[StartSynthesis, Depends(_get_use_case(StartSynthesis))]
FlagInfeasibleDep = Annotated[FlagInfeasible, Depends(_get_use_case(FlagInfeasible))]
CompleteSynthesisDep = Annotated[CompleteSynthesis, Depends(_get_use_case(CompleteSynthesis))]
FulfillSynthesisRequestDep = Annotated[FulfillSynthesisRequest, Depends(_get_use_case(FulfillSynthesisRequest))]
FailSynthesisDep = Annotated[FailSynthesis, Depends(_get_use_case(FailSynthesis))]
CancelSynthesisRequestDep = Annotated[CancelSynthesisRequest, Depends(_get_use_case(CancelSynthesisRequest))]
GetSynthesisRequestDep = Annotated[GetSynthesisRequest, Depends(_get_use_case(GetSynthesisRequest))]
UpdateSynthesisRequestDep = Annotated[UpdateSynthesisRequest, Depends(_get_use_case(UpdateSynthesisRequest))]
DeleteSynthesisRequestDep = Annotated[DeleteSynthesisRequest, Depends(_get_use_case(DeleteSynthesisRequest))]
ListSynthesisRequestsDep = Annotated[ListSynthesisRequests, Depends(_get_use_case(ListSynthesisRequests))]


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/synthesis-requests", response_model=SynthesisRequestResponse, status_code=201)
async def create_synthesis_request(
    body: CreateSynthesisRequestRequest, auth: AuthDep, uc: CreateSynthesisRequestDep
) -> SynthesisRequestResponse:
    result = await uc(
        CreateSynthesisRequestCommand(
            workspace_id=auth.workspace_id,
            requester_id=auth.user_id,
            molecule_id=body.molecule_id,
            amount_value=body.amount_value,
            amount_unit=body.amount_unit,
            purpose=body.purpose,
            priority=body.priority,
            target_purity=body.target_purity,
            project_id=body.project_id,
            parent_request_id=body.parent_request_id,
        ),
        auth=auth,
    )
    request = result_to_response(result)
    return SynthesisRequestResponse.from_domain(request)


@router.get("/synthesis-requests", response_model=list[SynthesisRequestSummaryResponse])
async def list_synthesis_requests(
    auth: AuthDep,
    uc: ListSynthesisRequestsDep,
    status: str | None = None,
    molecule_id: uuid.UUID | None = None,
) -> list[SynthesisRequestSummaryResponse]:
    result = await uc(
        ListSynthesisRequestsQuery(
            workspace_id=auth.workspace_id, status=status, molecule_id=molecule_id
        ),
        auth=auth,
    )
    requests = result_to_response(result)
    return [SynthesisRequestSummaryResponse.from_domain(r) for r in requests]


@router.get("/synthesis-requests/{request_id}", response_model=SynthesisRequestResponse)
async def get_synthesis_request(
    request_id: uuid.UUID, auth: AuthDep, uc: GetSynthesisRequestDep
) -> SynthesisRequestResponse:
    result = await uc(GetSynthesisRequestQuery(request_id=request_id), auth=auth)
    request = result_to_response(result)
    return SynthesisRequestResponse.from_domain(request)


@router.patch("/synthesis-requests/{request_id}", response_model=SynthesisRequestResponse)
async def update_synthesis_request(
    request_id: uuid.UUID,
    body: UpdateSynthesisRequestRequest,
    auth: AuthDep,
    uc: UpdateSynthesisRequestDep,
) -> SynthesisRequestResponse:
    from chem_vault.application.shared.sentinel import UNSET

    cmd = UpdateSynthesisRequestCommand(
        request_id=request_id,
        purpose=body.purpose if "purpose" in body.model_fields_set else UNSET,
        priority=body.priority if "priority" in body.model_fields_set else UNSET,
        amount_value=body.amount_value if "amount_value" in body.model_fields_set else UNSET,
        amount_unit=body.amount_unit if "amount_unit" in body.model_fields_set else UNSET,
        target_purity=body.target_purity if "target_purity" in body.model_fields_set else UNSET,
    )
    result = await uc(cmd, auth=auth)
    request = result_to_response(result)
    return SynthesisRequestResponse.from_domain(request)


@router.delete("/synthesis-requests/{request_id}", status_code=204)
async def delete_synthesis_request(
    request_id: uuid.UUID, auth: AuthDep, uc: DeleteSynthesisRequestDep
) -> None:
    result = await uc(DeleteSynthesisRequestCommand(request_id=request_id), auth=auth)
    result_to_response(result)


@router.post("/synthesis-requests/{request_id}/submit", response_model=SynthesisRequestResponse)
async def submit_synthesis_request(
    request_id: uuid.UUID, auth: AuthDep, uc: SubmitSynthesisRequestDep
) -> SynthesisRequestResponse:
    result = await uc(
        SubmitSynthesisRequestCommand(request_id=request_id),
        auth=auth,
    )
    request = result_to_response(result)
    return SynthesisRequestResponse.from_domain(request)


@router.post("/synthesis-requests/{request_id}/approve", response_model=SynthesisRequestResponse)
async def approve_synthesis_request(
    request_id: uuid.UUID, auth: AuthDep, uc: ApproveSynthesisRequestDep
) -> SynthesisRequestResponse:
    result = await uc(
        ApproveSynthesisRequestCommand(request_id=request_id, approved_by=auth.user_id),
        auth=auth,
    )
    request = result_to_response(result)
    return SynthesisRequestResponse.from_domain(request)


@router.post("/synthesis-requests/{request_id}/reject", response_model=SynthesisRequestResponse)
async def reject_synthesis_request(
    request_id: uuid.UUID, body: RejectRequest, auth: AuthDep, uc: RejectSynthesisRequestDep
) -> SynthesisRequestResponse:
    result = await uc(
        RejectSynthesisRequestCommand(
            request_id=request_id, reason=body.reason, rejected_by=auth.user_id
        ),
        auth=auth,
    )
    request = result_to_response(result)
    return SynthesisRequestResponse.from_domain(request)


@router.post("/synthesis-requests/{request_id}/assign", response_model=SynthesisRequestResponse)
async def assign_synthesis_request(
    request_id: uuid.UUID, body: AssignRequest, auth: AuthDep, uc: AssignSynthesisRequestDep
) -> SynthesisRequestResponse:
    # Auto-fill assigned_to with current user for internal assignments
    assigned_to = body.assigned_to
    if body.assignment_type == "internal" and assigned_to is None:
        assigned_to = auth.user_id
    result = await uc(
        AssignSynthesisRequestCommand(
            request_id=request_id,
            assignment_type=body.assignment_type,
            assigned_to=assigned_to,
            assigned_org_id=body.assigned_org_id,
        ),
        auth=auth,
    )
    request = result_to_response(result)
    return SynthesisRequestResponse.from_domain(request)


@router.post("/synthesis-requests/{request_id}/start", response_model=SynthesisRequestResponse)
async def start_synthesis(
    request_id: uuid.UUID, body: StartRequest, auth: AuthDep, uc: StartSynthesisDep
) -> SynthesisRequestResponse:
    result = await uc(
        StartSynthesisCommand(
            request_id=request_id, proposed_route_id=body.proposed_route_id
        ),
        auth=auth,
    )
    request = result_to_response(result)
    return SynthesisRequestResponse.from_domain(request)


@router.post("/synthesis-requests/{request_id}/flag-infeasible", response_model=SynthesisRequestResponse)
async def flag_infeasible(
    request_id: uuid.UUID, body: FlagInfeasibleRequest, auth: AuthDep, uc: FlagInfeasibleDep
) -> SynthesisRequestResponse:
    result = await uc(
        FlagInfeasibleCommand(
            request_id=request_id,
            feasibility_status=body.feasibility_status,
            feasibility_notes=body.feasibility_notes,
        ),
        auth=auth,
    )
    request = result_to_response(result)
    return SynthesisRequestResponse.from_domain(request)


@router.post("/synthesis-requests/{request_id}/complete", response_model=SynthesisRequestResponse)
async def complete_synthesis(
    request_id: uuid.UUID, body: CompleteRequest, auth: AuthDep, uc: CompleteSynthesisDep
) -> SynthesisRequestResponse:
    result = await uc(
        CompleteSynthesisCommand(
            request_id=request_id,
            actual_cost_value=body.actual_cost_value,
            actual_cost_unit=body.actual_cost_unit,
        ),
        auth=auth,
    )
    request = result_to_response(result)
    return SynthesisRequestResponse.from_domain(request)


@router.post("/synthesis-requests/{request_id}/fulfill", response_model=SynthesisRequestResponse)
async def fulfill_synthesis_request(
    request_id: uuid.UUID, body: FulfillRequest, auth: AuthDep, uc: FulfillSynthesisRequestDep
) -> SynthesisRequestResponse:
    result = await uc(
        FulfillSynthesisRequestCommand(request_id=request_id, batch_id=body.batch_id),
        auth=auth,
    )
    request = result_to_response(result)
    return SynthesisRequestResponse.from_domain(request)


@router.post("/synthesis-requests/{request_id}/fail", response_model=SynthesisRequestResponse)
async def fail_synthesis(
    request_id: uuid.UUID, body: FailRequest, auth: AuthDep, uc: FailSynthesisDep
) -> SynthesisRequestResponse:
    result = await uc(
        FailSynthesisCommand(request_id=request_id, reason=body.reason),
        auth=auth,
    )
    request = result_to_response(result)
    return SynthesisRequestResponse.from_domain(request)


@router.post("/synthesis-requests/{request_id}/cancel", response_model=SynthesisRequestResponse)
async def cancel_synthesis_request(
    request_id: uuid.UUID, auth: AuthDep, uc: CancelSynthesisRequestDep
) -> SynthesisRequestResponse:
    result = await uc(
        CancelSynthesisRequestCommand(request_id=request_id),
        auth=auth,
    )
    request = result_to_response(result)
    return SynthesisRequestResponse.from_domain(request)
