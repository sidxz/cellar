"""Run API routes."""

from __future__ import annotations

import uuid
from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from lagom import Container
from pydantic import BaseModel

from chem_vault.application.screening.create_run import CreateRun, CreateRunCommand
from chem_vault.application.screening.get_run import GetRun, ListRunsByProtocol
from chem_vault.application.screening.lock_run import LockRun, UnlockRun
from chem_vault.application.screening.manage_run import ApproveRun, CompleteRun, RejectRun, StartRun
from chem_vault.interface.dependencies import AuthDep, get_container
from chem_vault.interface.error_handlers import result_to_response

router = APIRouter(prefix="/api/v1", tags=["runs"])


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class RunResponse(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    protocol_id: uuid.UUID
    run_date: date
    operator: uuid.UUID
    status: str
    is_locked: bool
    locked_by: uuid.UUID | None = None
    lock_reason: str | None = None
    qc_metrics: dict[str, Any] | None = None
    notes: str | None = None
    plate_count: int
    performed_at_org_id: uuid.UUID | None = None
    parent_run_id: uuid.UUID | None = None
    run_relationship_type: str | None = None
    plate_format: str | None = None
    conditions: dict[str, Any] | None = None

    @classmethod
    def from_domain(cls, r) -> RunResponse:  # type: ignore[no-untyped-def]
        return cls(
            id=r.id,
            workspace_id=r.workspace_id,
            protocol_id=r.protocol_id,
            run_date=r.run_date,
            operator=r.operator,
            status=r.status.value,
            is_locked=r.is_locked,
            locked_by=r.locked_by,
            lock_reason=r.lock_reason,
            qc_metrics=r.qc_metrics,
            notes=r.notes,
            plate_count=len(r.plates),
            performed_at_org_id=r.performed_at_org_id,
            parent_run_id=r.parent_run_id,
            run_relationship_type=r.run_relationship_type.value if r.run_relationship_type else None,
            plate_format=r.plate_format.value if r.plate_format else None,
            conditions=r.conditions,
        )


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------


class CreateRunRequest(BaseModel):
    protocol_id: uuid.UUID
    run_date: date
    performed_at_org_id: uuid.UUID | None = None
    parent_run_id: uuid.UUID | None = None
    run_relationship_type: str | None = None
    plate_format: str | None = None
    conditions: dict[str, Any] | None = None
    notes: str | None = None


class CompleteRunRequest(BaseModel):
    plate_count: int = 0
    data_point_count: int = 0


class RejectRequest(BaseModel):
    reason: str


class LockRequest(BaseModel):
    reason: str


class UnlockRequest(BaseModel):
    reason: str


# ---------------------------------------------------------------------------
# Dependency resolvers
# ---------------------------------------------------------------------------


def _create_run(c: Annotated[Container, Depends(get_container)]) -> CreateRun:
    return c[CreateRun]

def _get_run(c: Annotated[Container, Depends(get_container)]) -> GetRun:
    return c[GetRun]

def _list_runs(c: Annotated[Container, Depends(get_container)]) -> ListRunsByProtocol:
    return c[ListRunsByProtocol]

def _start_run(c: Annotated[Container, Depends(get_container)]) -> StartRun:
    return c[StartRun]

def _complete_run(c: Annotated[Container, Depends(get_container)]) -> CompleteRun:
    return c[CompleteRun]

def _approve_run(c: Annotated[Container, Depends(get_container)]) -> ApproveRun:
    return c[ApproveRun]

def _reject_run(c: Annotated[Container, Depends(get_container)]) -> RejectRun:
    return c[RejectRun]

def _lock_run(c: Annotated[Container, Depends(get_container)]) -> LockRun:
    return c[LockRun]

def _unlock_run(c: Annotated[Container, Depends(get_container)]) -> UnlockRun:
    return c[UnlockRun]


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.post("/runs", response_model=RunResponse, status_code=201)
async def create_run(
    auth: AuthDep,
    body: CreateRunRequest,
    uc: Annotated[CreateRun, Depends(_create_run)],
) -> RunResponse:
    cmd = CreateRunCommand(
        workspace_id=auth.workspace_id,
        protocol_id=body.protocol_id,
        run_date=body.run_date,
        performed_at_org_id=body.performed_at_org_id,
        parent_run_id=body.parent_run_id,
        run_relationship_type=body.run_relationship_type,
        plate_format=body.plate_format,
        conditions=body.conditions,
        notes=body.notes,
    )
    result = await uc(cmd, auth=auth)
    return RunResponse.from_domain(result_to_response(result))


@router.get("/protocols/{protocol_id}/runs", response_model=list[RunResponse])
async def list_runs_by_protocol(
    protocol_id: uuid.UUID,
    auth: AuthDep,
    uc: Annotated[ListRunsByProtocol, Depends(_list_runs)],
) -> list[RunResponse]:
    result = await uc(protocol_id, auth=auth)
    runs = result_to_response(result)
    return [RunResponse.from_domain(r) for r in runs]


@router.get("/runs/{run_id}", response_model=RunResponse)
async def get_run(
    run_id: uuid.UUID,
    auth: AuthDep,
    uc: Annotated[GetRun, Depends(_get_run)],
) -> RunResponse:
    result = await uc(run_id, auth=auth)
    return RunResponse.from_domain(result_to_response(result))


@router.post("/runs/{run_id}/start", response_model=RunResponse)
async def start_run(
    run_id: uuid.UUID,
    auth: AuthDep,
    uc: Annotated[StartRun, Depends(_start_run)],
) -> RunResponse:
    result = await uc(run_id, auth=auth)
    return RunResponse.from_domain(result_to_response(result))


@router.post("/runs/{run_id}/complete", response_model=RunResponse)
async def complete_run(
    run_id: uuid.UUID,
    auth: AuthDep,
    body: CompleteRunRequest,
    uc: Annotated[CompleteRun, Depends(_complete_run)],
) -> RunResponse:
    result = await uc(run_id, plate_count=body.plate_count, data_point_count=body.data_point_count, auth=auth)
    return RunResponse.from_domain(result_to_response(result))


@router.post("/runs/{run_id}/approve", response_model=RunResponse)
async def approve_run(
    run_id: uuid.UUID,
    auth: AuthDep,
    uc: Annotated[ApproveRun, Depends(_approve_run)],
) -> RunResponse:
    result = await uc(run_id, auth=auth)
    return RunResponse.from_domain(result_to_response(result))


@router.post("/runs/{run_id}/reject", response_model=RunResponse)
async def reject_run(
    run_id: uuid.UUID,
    auth: AuthDep,
    body: RejectRequest,
    uc: Annotated[RejectRun, Depends(_reject_run)],
) -> RunResponse:
    result = await uc(run_id, reason=body.reason, auth=auth)
    return RunResponse.from_domain(result_to_response(result))


@router.post("/runs/{run_id}/lock", response_model=RunResponse)
async def lock_run(
    run_id: uuid.UUID,
    auth: AuthDep,
    body: LockRequest,
    uc: Annotated[LockRun, Depends(_lock_run)],
) -> RunResponse:
    result = await uc(run_id, reason=body.reason, auth=auth)
    return RunResponse.from_domain(result_to_response(result))


@router.post("/runs/{run_id}/unlock", response_model=RunResponse)
async def unlock_run(
    run_id: uuid.UUID,
    auth: AuthDep,
    body: UnlockRequest,
    uc: Annotated[UnlockRun, Depends(_unlock_run)],
) -> RunResponse:
    result = await uc(run_id, reason=body.reason, auth=auth)
    return RunResponse.from_domain(result_to_response(result))
