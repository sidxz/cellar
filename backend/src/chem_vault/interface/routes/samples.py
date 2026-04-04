"""Sample API routes."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from lagom import Container
from pydantic import BaseModel

from chem_vault.application.inventory.create_sample import CreateSample, CreateSampleCommand
from chem_vault.application.inventory.get_sample import GetSample, ListSamplesByBatch
from chem_vault.application.inventory.manage_sample import (
    AliquotSample,
    ClearQuarantineSample,
    DisposeSample,
    MoveSample,
    QuarantineSample,
)
from chem_vault.interface.dependencies import AuthDep, get_container
from chem_vault.interface.error_handlers import result_to_response

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


# --- Deps ---

def _create_sample(c: Annotated[Container, Depends(get_container)]) -> CreateSample:
    return c[CreateSample]

def _get_sample(c: Annotated[Container, Depends(get_container)]) -> GetSample:
    return c[GetSample]

def _list_samples(c: Annotated[Container, Depends(get_container)]) -> ListSamplesByBatch:
    return c[ListSamplesByBatch]

def _aliquot(c: Annotated[Container, Depends(get_container)]) -> AliquotSample:
    return c[AliquotSample]

def _move(c: Annotated[Container, Depends(get_container)]) -> MoveSample:
    return c[MoveSample]

def _quarantine(c: Annotated[Container, Depends(get_container)]) -> QuarantineSample:
    return c[QuarantineSample]

def _clear_quarantine(c: Annotated[Container, Depends(get_container)]) -> ClearQuarantineSample:
    return c[ClearQuarantineSample]

def _dispose(c: Annotated[Container, Depends(get_container)]) -> DisposeSample:
    return c[DisposeSample]


# --- Routes ---


@router.post("/samples", response_model=SampleResponse, status_code=201)
async def create_sample(
    auth: AuthDep,
    body: CreateSampleRequest,
    uc: Annotated[CreateSample, Depends(_create_sample)],
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
    uc: Annotated[GetSample, Depends(_get_sample)],
) -> SampleResponse:
    result = await uc(sample_id, auth=auth)
    return SampleResponse.from_domain(result_to_response(result))


@router.get("/batches/{batch_id}/samples", response_model=list[SampleResponse])
async def list_samples_by_batch(
    batch_id: uuid.UUID,
    auth: AuthDep,
    uc: Annotated[ListSamplesByBatch, Depends(_list_samples)],
) -> list[SampleResponse]:
    result = await uc(batch_id, auth=auth)
    samples = result_to_response(result)
    return [SampleResponse.from_domain(s) for s in samples]


@router.post("/samples/{sample_id}/aliquot", response_model=SampleResponse)
async def aliquot_sample(
    sample_id: uuid.UUID,
    body: AliquotRequest,
    auth: AuthDep,
    uc: Annotated[AliquotSample, Depends(_aliquot)],
) -> SampleResponse:
    result = await uc(sample_id, body.amount, auth=auth)
    return SampleResponse.from_domain(result_to_response(result))


@router.post("/samples/{sample_id}/move", response_model=SampleResponse)
async def move_sample(
    sample_id: uuid.UUID,
    body: MoveRequest,
    auth: AuthDep,
    uc: Annotated[MoveSample, Depends(_move)],
) -> SampleResponse:
    result = await uc(sample_id, body.location_id, auth=auth)
    return SampleResponse.from_domain(result_to_response(result))


@router.post("/samples/{sample_id}/quarantine", response_model=SampleResponse)
async def quarantine_sample(
    sample_id: uuid.UUID,
    body: QuarantineRequest,
    auth: AuthDep,
    uc: Annotated[QuarantineSample, Depends(_quarantine)],
) -> SampleResponse:
    result = await uc(sample_id, body.reason, auth=auth)
    return SampleResponse.from_domain(result_to_response(result))


@router.post("/samples/{sample_id}/clear-quarantine", response_model=SampleResponse)
async def clear_quarantine_sample(
    sample_id: uuid.UUID,
    auth: AuthDep,
    uc: Annotated[ClearQuarantineSample, Depends(_clear_quarantine)],
) -> SampleResponse:
    result = await uc(sample_id, auth=auth)
    return SampleResponse.from_domain(result_to_response(result))


@router.post("/samples/{sample_id}/dispose", response_model=SampleResponse)
async def dispose_sample(
    sample_id: uuid.UUID,
    body: DisposeRequest,
    auth: AuthDep,
    uc: Annotated[DisposeSample, Depends(_dispose)],
) -> SampleResponse:
    result = await uc(sample_id, body.reason, auth=auth)
    return SampleResponse.from_domain(result_to_response(result))
