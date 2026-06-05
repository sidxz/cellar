"""SampleRequest API routes."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from cellar.application.inventory.sample_requests import (
    ApproveSampleRequest,
    ApproveSampleRequestCommand,
    CancelSampleRequest,
    CancelSampleRequestCommand,
    CreateSampleRequest,
    CreateSampleRequestCommand,
    FulfillSampleRequest,
    FulfillSampleRequestCommand,
    GetSampleRequest,
    GetSampleRequestQuery,
    ListSampleRequests,
    ListSampleRequestsQuery,
    RejectSampleRequest,
    RejectSampleRequestCommand,
    StartPreparingSampleRequest,
    StartPreparingSampleRequestCommand,
    UpdateSampleRequest,
    UpdateSampleRequestCommand,
)
from cellar.application.shared.sentinel import UNSET
from cellar.domain.inventory.sample_request import SampleRequest
from cellar.interface.dependencies import AuthDep, _get_use_case
from cellar.interface.error_handlers import result_to_response

router = APIRouter(prefix="/api/v1", tags=["sample-requests"])


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class SampleRequestResponse(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    requester_id: uuid.UUID
    molecule_id: uuid.UUID
    batch_id: uuid.UUID | None = None
    amount_value: float
    amount_unit: str
    purpose: str
    priority: str
    status: str
    assigned_to: uuid.UUID | None = None
    fulfilled_sample_id: uuid.UUID | None = None
    rejection_reason: str | None = None
    fulfilled_at: str | None = None

    @classmethod
    def from_domain(cls, r: SampleRequest) -> SampleRequestResponse:
        return cls(
            id=r.id,
            workspace_id=r.workspace_id,
            requester_id=r.requester_id,
            molecule_id=r.molecule_id,
            batch_id=r.batch_id,
            amount_value=r.requested_amount.value,
            amount_unit=r.requested_amount.unit.value,
            purpose=r.purpose,
            priority=r.priority.value,
            status=r.status.value,
            assigned_to=r.assigned_to,
            fulfilled_sample_id=r.fulfilled_sample_id,
            rejection_reason=r.rejection_reason,
            fulfilled_at=r.fulfilled_at.isoformat() if r.fulfilled_at else None,
        )


# ---------------------------------------------------------------------------
# Request bodies
# ---------------------------------------------------------------------------


class CreateSampleRequestRequest(BaseModel):
    molecule_id: uuid.UUID
    batch_id: uuid.UUID | None = None
    amount_value: float
    amount_unit: str
    purpose: str
    priority: str = "routine"


class ApproveRequest(BaseModel):
    assigned_to: uuid.UUID | None = None


class RejectRequest(BaseModel):
    reason: str


class FulfillRequest(BaseModel):
    sample_id: uuid.UUID


class UpdateSampleRequestRequest(BaseModel):
    purpose: str | None = None
    priority: str | None = None
    amount_value: float | None = None
    amount_unit: str | None = None


# ---------------------------------------------------------------------------
# Dependencies
# ---------------------------------------------------------------------------


CreateSampleRequestDep = Annotated[
    CreateSampleRequest, Depends(_get_use_case(CreateSampleRequest))
]
GetSampleRequestDep = Annotated[GetSampleRequest, Depends(_get_use_case(GetSampleRequest))]
ListSampleRequestsDep = Annotated[ListSampleRequests, Depends(_get_use_case(ListSampleRequests))]
ApproveSampleRequestDep = Annotated[
    ApproveSampleRequest, Depends(_get_use_case(ApproveSampleRequest))
]
RejectSampleRequestDep = Annotated[
    RejectSampleRequest, Depends(_get_use_case(RejectSampleRequest))
]
StartPreparingSampleRequestDep = Annotated[
    StartPreparingSampleRequest, Depends(_get_use_case(StartPreparingSampleRequest))
]
FulfillSampleRequestDep = Annotated[
    FulfillSampleRequest, Depends(_get_use_case(FulfillSampleRequest))
]
CancelSampleRequestDep = Annotated[
    CancelSampleRequest, Depends(_get_use_case(CancelSampleRequest))
]
UpdateSampleRequestDep = Annotated[
    UpdateSampleRequest, Depends(_get_use_case(UpdateSampleRequest))
]


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/sample-requests", response_model=SampleRequestResponse, status_code=201)
async def create_sample_request(
    body: CreateSampleRequestRequest, auth: AuthDep, uc: CreateSampleRequestDep
) -> SampleRequestResponse:
    result = await uc(
        CreateSampleRequestCommand(
            workspace_id=auth.workspace_id,
            requester_id=auth.user_id,
            molecule_id=body.molecule_id,
            batch_id=body.batch_id,
            amount_value=body.amount_value,
            amount_unit=body.amount_unit,
            purpose=body.purpose,
            priority=body.priority,
        ),
        auth=auth,
    )
    request = result_to_response(result)
    return SampleRequestResponse.from_domain(request)


@router.get("/sample-requests", response_model=list[SampleRequestResponse])
async def list_sample_requests(
    auth: AuthDep, uc: ListSampleRequestsDep, status: str | None = None
) -> list[SampleRequestResponse]:
    result = await uc(
        ListSampleRequestsQuery(workspace_id=auth.workspace_id, status=status),
        auth=auth,
    )
    requests = result_to_response(result)
    return [SampleRequestResponse.from_domain(r) for r in requests]


@router.get("/sample-requests/{request_id}", response_model=SampleRequestResponse)
async def get_sample_request(
    request_id: uuid.UUID, auth: AuthDep, uc: GetSampleRequestDep
) -> SampleRequestResponse:
    result = await uc(
        GetSampleRequestQuery(workspace_id=auth.workspace_id, request_id=request_id), auth=auth
    )
    request = result_to_response(result)
    return SampleRequestResponse.from_domain(request)


@router.patch("/sample-requests/{request_id}", response_model=SampleRequestResponse)
async def update_sample_request(
    request_id: uuid.UUID,
    body: UpdateSampleRequestRequest,
    auth: AuthDep,
    uc: UpdateSampleRequestDep,
) -> SampleRequestResponse:

    cmd = UpdateSampleRequestCommand(
        workspace_id=auth.workspace_id,
        request_id=request_id,
        purpose=body.purpose if "purpose" in body.model_fields_set else UNSET,
        priority=body.priority if "priority" in body.model_fields_set else UNSET,
        amount_value=body.amount_value if "amount_value" in body.model_fields_set else UNSET,
        amount_unit=body.amount_unit if "amount_unit" in body.model_fields_set else UNSET,
    )
    result = await uc(cmd, auth=auth)
    request = result_to_response(result)
    return SampleRequestResponse.from_domain(request)


@router.post("/sample-requests/{request_id}/approve", response_model=SampleRequestResponse)
async def approve_sample_request(
    request_id: uuid.UUID, body: ApproveRequest, auth: AuthDep, uc: ApproveSampleRequestDep
) -> SampleRequestResponse:
    # Auto-fill assigned_to with current user when not specified
    assigned_to = body.assigned_to if body.assigned_to is not None else auth.user_id
    result = await uc(
        ApproveSampleRequestCommand(
            workspace_id=auth.workspace_id, request_id=request_id, assigned_to=assigned_to
        ),
        auth=auth,
    )
    request = result_to_response(result)
    return SampleRequestResponse.from_domain(request)


@router.post("/sample-requests/{request_id}/reject", response_model=SampleRequestResponse)
async def reject_sample_request(
    request_id: uuid.UUID, body: RejectRequest, auth: AuthDep, uc: RejectSampleRequestDep
) -> SampleRequestResponse:
    result = await uc(
        RejectSampleRequestCommand(
            workspace_id=auth.workspace_id, request_id=request_id, reason=body.reason
        ),
        auth=auth,
    )
    request = result_to_response(result)
    return SampleRequestResponse.from_domain(request)


@router.post("/sample-requests/{request_id}/prepare", response_model=SampleRequestResponse)
async def start_preparing_sample_request(
    request_id: uuid.UUID, auth: AuthDep, uc: StartPreparingSampleRequestDep
) -> SampleRequestResponse:
    result = await uc(
        StartPreparingSampleRequestCommand(workspace_id=auth.workspace_id, request_id=request_id),
        auth=auth,
    )
    request = result_to_response(result)
    return SampleRequestResponse.from_domain(request)


@router.post("/sample-requests/{request_id}/fulfill", response_model=SampleRequestResponse)
async def fulfill_sample_request(
    request_id: uuid.UUID, body: FulfillRequest, auth: AuthDep, uc: FulfillSampleRequestDep
) -> SampleRequestResponse:
    result = await uc(
        FulfillSampleRequestCommand(
            workspace_id=auth.workspace_id, request_id=request_id, sample_id=body.sample_id
        ),
        auth=auth,
    )
    request = result_to_response(result)
    return SampleRequestResponse.from_domain(request)


@router.post("/sample-requests/{request_id}/cancel", response_model=SampleRequestResponse)
async def cancel_sample_request(
    request_id: uuid.UUID, auth: AuthDep, uc: CancelSampleRequestDep
) -> SampleRequestResponse:
    result = await uc(
        CancelSampleRequestCommand(workspace_id=auth.workspace_id, request_id=request_id),
        auth=auth,
    )
    request = result_to_response(result)
    return SampleRequestResponse.from_domain(request)
