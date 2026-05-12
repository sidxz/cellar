"""Sample API routes."""

from __future__ import annotations

import uuid

from fastapi import APIRouter
from pydantic import BaseModel

from cellar.application.inventory.create_sample import CreateSample, CreateSampleCommand
from cellar.application.inventory.get_sample import (
    GetSample,
    GetSampleQuery,
    ListSamplesByBatch,
    ListSamplesByBatchQuery,
)
from cellar.application.inventory.manage_sample import (
    AliquotSample,
    AliquotSampleCommand,
    ClearQuarantineSample,
    ClearQuarantineSampleCommand,
    DisposeSample,
    DisposeSampleCommand,
    MoveSample,
    MoveSampleCommand,
    QuarantineSample,
    QuarantineSampleCommand,
)
from cellar.interface.dependencies import (
    AliquotSampleDep,
    AuthDep,
    ClearQuarantineSampleDep,
    CreateSampleDep,
    DisposeSampleDep,
    GetSampleDep,
    ListSamplesByBatchDep,
    MoveSampleDep,
    QuarantineSampleDep,
)
from cellar.interface.error_handlers import result_to_response

router = APIRouter(prefix="/api/v1", tags=["samples"])


class SampleResponse(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    batch_id: uuid.UUID
    barcode: str
    container_type: str
    amount_value: float
    amount_unit: str
    solvent: str | None = None
    status: str
    location_id: uuid.UUID | None = None
    freeze_thaw_count: int = 0
    low_stock_threshold: float | None = None

    @classmethod
    def from_domain(cls, s) -> SampleResponse:  # type: ignore[no-untyped-def]
        return cls(
            id=s.id,
            workspace_id=s.workspace_id,
            batch_id=s.batch_id,
            barcode=s.barcode.value,
            container_type=s.container_type.value,
            amount_value=s.amount.value,
            amount_unit=s.amount.unit.value,
            solvent=s.solvent,
            status=s.status.value,
            location_id=s.location_id,
            freeze_thaw_count=s.freeze_thaw_count,
            low_stock_threshold=s.low_stock_threshold,
        )


class CreateSampleRequest(BaseModel):
    batch_id: uuid.UUID
    barcode: str
    container_type: str
    amount_value: float
    amount_unit: str
    concentration_value: float | None = None
    concentration_unit: str | None = None
    solvent: str | None = None
    location_id: uuid.UUID | None = None
    low_stock_threshold: float | None = None


class AliquotRequest(BaseModel):
    amount: float


class MoveRequest(BaseModel):
    location_id: uuid.UUID | None = None


class QuarantineRequest(BaseModel):
    reason: str


class DisposeRequest(BaseModel):
    reason: str | None = None


# --- Routes ---


@router.post("/samples", response_model=SampleResponse, status_code=201)
async def create_sample(
    auth: AuthDep,
    body: CreateSampleRequest,
    uc: CreateSampleDep,
) -> SampleResponse:
    cmd = CreateSampleCommand(
        workspace_id=auth.workspace_id,
        batch_id=body.batch_id,
        barcode=body.barcode,
        container_type=body.container_type,
        amount_value=body.amount_value,
        amount_unit=body.amount_unit,
        concentration_value=body.concentration_value,
        concentration_unit=body.concentration_unit,
        solvent=body.solvent,
        location_id=body.location_id,
        low_stock_threshold=body.low_stock_threshold,
    )
    result = await uc(cmd, auth=auth)
    return SampleResponse.from_domain(result_to_response(result))


@router.get("/samples/{sample_id}", response_model=SampleResponse)
async def get_sample(
    sample_id: uuid.UUID,
    auth: AuthDep,
    uc: GetSampleDep,
) -> SampleResponse:
    result = await uc(
        GetSampleQuery(workspace_id=auth.workspace_id, sample_id=sample_id),
        auth=auth,
    )
    return SampleResponse.from_domain(result_to_response(result))


@router.get("/batches/{batch_id}/samples", response_model=list[SampleResponse])
async def list_samples_by_batch(
    batch_id: uuid.UUID,
    auth: AuthDep,
    uc: ListSamplesByBatchDep,
) -> list[SampleResponse]:
    result = await uc(
        ListSamplesByBatchQuery(workspace_id=auth.workspace_id, batch_id=batch_id),
        auth=auth,
    )
    samples = result_to_response(result)
    return [SampleResponse.from_domain(s) for s in samples]


@router.post("/samples/{sample_id}/aliquot", response_model=SampleResponse)
async def aliquot_sample(
    sample_id: uuid.UUID,
    body: AliquotRequest,
    auth: AuthDep,
    uc: AliquotSampleDep,
) -> SampleResponse:
    result = await uc(
        AliquotSampleCommand(
            workspace_id=auth.workspace_id,
            sample_id=sample_id,
            amount=body.amount,
        ),
        auth=auth,
    )
    return SampleResponse.from_domain(result_to_response(result))


@router.post("/samples/{sample_id}/move", response_model=SampleResponse)
async def move_sample(
    sample_id: uuid.UUID,
    body: MoveRequest,
    auth: AuthDep,
    uc: MoveSampleDep,
) -> SampleResponse:
    result = await uc(
        MoveSampleCommand(
            workspace_id=auth.workspace_id,
            sample_id=sample_id,
            location_id=body.location_id,
        ),
        auth=auth,
    )
    return SampleResponse.from_domain(result_to_response(result))


@router.post("/samples/{sample_id}/quarantine", response_model=SampleResponse)
async def quarantine_sample(
    sample_id: uuid.UUID,
    body: QuarantineRequest,
    auth: AuthDep,
    uc: QuarantineSampleDep,
) -> SampleResponse:
    result = await uc(
        QuarantineSampleCommand(
            workspace_id=auth.workspace_id,
            sample_id=sample_id,
            reason=body.reason,
        ),
        auth=auth,
    )
    return SampleResponse.from_domain(result_to_response(result))


@router.post("/samples/{sample_id}/clear-quarantine", response_model=SampleResponse)
async def clear_quarantine_sample(
    sample_id: uuid.UUID,
    auth: AuthDep,
    uc: ClearQuarantineSampleDep,
) -> SampleResponse:
    result = await uc(
        ClearQuarantineSampleCommand(workspace_id=auth.workspace_id, sample_id=sample_id),
        auth=auth,
    )
    return SampleResponse.from_domain(result_to_response(result))


@router.post("/samples/{sample_id}/dispose", response_model=SampleResponse)
async def dispose_sample(
    sample_id: uuid.UUID,
    body: DisposeRequest,
    auth: AuthDep,
    uc: DisposeSampleDep,
) -> SampleResponse:
    result = await uc(
        DisposeSampleCommand(
            workspace_id=auth.workspace_id,
            sample_id=sample_id,
            reason=body.reason,
        ),
        auth=auth,
    )
    return SampleResponse.from_domain(result_to_response(result))
