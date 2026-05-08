"""Run API routes."""

from __future__ import annotations

import uuid
from datetime import date
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from chem_vault.application.screening.create_run import CreateRun, CreateRunCommand
from chem_vault.application.screening.delete_run import DeleteRun, DeleteRunCommand
from chem_vault.application.screening.reset_run_data import (
    ResetRunData,
    ResetRunDataCommand,
)
from chem_vault.application.screening.get_run import GetRun, GetRunQuery
from chem_vault.application.screening.list_runs_with_counts import ListRunsWithCounts, ListRunsWithCountsQuery
from chem_vault.application.screening.lock_run import LockRun, LockRunCommand, UnlockRun, UnlockRunCommand
from chem_vault.application.screening.manage_run import (
    ApproveRun,
    ApproveRunCommand,
    CompleteRun,
    CompleteRunCommand,
    RejectRun,
    RejectRunCommand,
    StartRun,
    StartRunCommand,
)
from chem_vault.application.screening.update_run import UpdateRun, UpdateRunCommand
from chem_vault.interface.dependencies import (
    ApproveRunDep,
    AuthDep,
    CompleteRunDep,
    CreateRunDep,
    DeleteRunDep,
    ResetRunDataDep,
    GetRunDep,
    ListRunsWithCountsDep,
    LockRunDep,
    RejectRunDep,
    StartRunDep,
    UnlockRunDep,
    UpdateRunDep,
)
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
    molecule_count: int = 0
    performed_at_org_id: uuid.UUID | None = None
    parent_run_id: uuid.UUID | None = None
    run_relationship_type: str | None = None
    plate_format: str | None = None
    plate_template_id: uuid.UUID | None = None
    conditions: dict[str, Any] | None = None

    @classmethod
    def from_domain(cls, r, *, molecule_count: int = 0) -> RunResponse:  # type: ignore[no-untyped-def]
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
            molecule_count=molecule_count,
            performed_at_org_id=r.performed_at_org_id,
            parent_run_id=r.parent_run_id,
            run_relationship_type=r.run_relationship_type.value if r.run_relationship_type else None,
            plate_format=r.plate_format.value if r.plate_format else None,
            plate_template_id=r.plate_template_id,
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
    plate_template_id: uuid.UUID | None = None
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


class UpdateRunRequest(BaseModel):
    qc_metrics: dict[str, Any] | None = None
    notes: str | None = None


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.post("/runs", response_model=RunResponse, status_code=201)
async def create_run(
    auth: AuthDep,
    body: CreateRunRequest,
    uc: CreateRunDep,
) -> RunResponse:
    cmd = CreateRunCommand(
        workspace_id=auth.workspace_id,
        protocol_id=body.protocol_id,
        run_date=body.run_date,
        performed_at_org_id=body.performed_at_org_id,
        parent_run_id=body.parent_run_id,
        run_relationship_type=body.run_relationship_type,
        plate_format=body.plate_format,
        plate_template_id=body.plate_template_id,
        conditions=body.conditions,
        notes=body.notes,
    )
    result = await uc(cmd, auth=auth)
    return RunResponse.from_domain(result_to_response(result))


@router.get("/protocols/{protocol_id}/runs", response_model=list[RunResponse])
async def list_runs_by_protocol(
    protocol_id: uuid.UUID,
    auth: AuthDep,
    uc: ListRunsWithCountsDep,
) -> list[RunResponse]:
    result = await uc(
        ListRunsWithCountsQuery(workspace_id=auth.workspace_id, protocol_id=protocol_id),
        auth=auth,
    )
    items = result_to_response(result)
    return [RunResponse.from_domain(item.run, molecule_count=item.molecule_count) for item in items]


@router.get("/runs/{run_id}", response_model=RunResponse)
async def get_run(
    run_id: uuid.UUID,
    auth: AuthDep,
    uc: GetRunDep,
) -> RunResponse:
    result = await uc(
        GetRunQuery(workspace_id=auth.workspace_id, run_id=run_id),
        auth=auth,
    )
    return RunResponse.from_domain(result_to_response(result))


@router.patch("/runs/{run_id}", response_model=RunResponse)
async def update_run(
    run_id: uuid.UUID,
    body: UpdateRunRequest,
    auth: AuthDep,
    uc: UpdateRunDep,
) -> RunResponse:
    from chem_vault.application.shared.sentinel import UNSET

    cmd = UpdateRunCommand(
        workspace_id=auth.workspace_id,
        run_id=run_id,
        qc_metrics=body.qc_metrics if "qc_metrics" in body.model_fields_set else UNSET,
        notes=body.notes if "notes" in body.model_fields_set else UNSET,
    )
    result = await uc(cmd, auth=auth)
    return RunResponse.from_domain(result_to_response(result))


@router.delete("/runs/{run_id}", status_code=204)
async def delete_run(
    run_id: uuid.UUID,
    auth: AuthDep,
    uc: DeleteRunDep,
) -> None:
    cmd = DeleteRunCommand(
        workspace_id=auth.workspace_id,
        run_id=run_id,
    )
    result = await uc(cmd, auth=auth)
    result_to_response(result)


class ResetRunDataResponse(BaseModel):
    plates_deleted: int
    wells_deleted: int
    readouts_deleted: int
    curves_deleted: int


@router.post("/runs/{run_id}/reset-data", response_model=ResetRunDataResponse)
async def reset_run_data(
    run_id: uuid.UUID,
    auth: AuthDep,
    uc: ResetRunDataDep,
) -> ResetRunDataResponse:
    """Wipe a run's plates, wells, readouts, dose-response curves, and QC.

    The run row itself, its metadata, and any attached files are kept.
    Only DRAFT and IN_PROGRESS runs may be reset. Locked or terminal
    runs are rejected.
    """
    cmd = ResetRunDataCommand(
        workspace_id=auth.workspace_id,
        run_id=run_id,
    )
    result = await uc(cmd, auth=auth)
    out = result_to_response(result)
    return ResetRunDataResponse(
        plates_deleted=out.plates_deleted,
        wells_deleted=out.wells_deleted,
        readouts_deleted=out.readouts_deleted,
        curves_deleted=out.curves_deleted,
    )


@router.post("/runs/{run_id}/start", response_model=RunResponse)
async def start_run(
    run_id: uuid.UUID,
    auth: AuthDep,
    uc: StartRunDep,
) -> RunResponse:
    result = await uc(StartRunCommand(workspace_id=auth.workspace_id, run_id=run_id), auth=auth)
    return RunResponse.from_domain(result_to_response(result))


@router.post("/runs/{run_id}/complete", response_model=RunResponse)
async def complete_run(
    run_id: uuid.UUID,
    auth: AuthDep,
    body: CompleteRunRequest,
    uc: CompleteRunDep,
) -> RunResponse:
    result = await uc(
        CompleteRunCommand(workspace_id=auth.workspace_id, run_id=run_id, plate_count=body.plate_count, data_point_count=body.data_point_count),
        auth=auth,
    )
    return RunResponse.from_domain(result_to_response(result))


@router.post("/runs/{run_id}/approve", response_model=RunResponse)
async def approve_run(
    run_id: uuid.UUID,
    auth: AuthDep,
    uc: ApproveRunDep,
) -> RunResponse:
    result = await uc(ApproveRunCommand(workspace_id=auth.workspace_id, run_id=run_id), auth=auth)
    return RunResponse.from_domain(result_to_response(result))


@router.post("/runs/{run_id}/reject", response_model=RunResponse)
async def reject_run(
    run_id: uuid.UUID,
    auth: AuthDep,
    body: RejectRequest,
    uc: RejectRunDep,
) -> RunResponse:
    result = await uc(RejectRunCommand(workspace_id=auth.workspace_id, run_id=run_id, reason=body.reason), auth=auth)
    return RunResponse.from_domain(result_to_response(result))


@router.post("/runs/{run_id}/lock", response_model=RunResponse)
async def lock_run(
    run_id: uuid.UUID,
    auth: AuthDep,
    body: LockRequest,
    uc: LockRunDep,
) -> RunResponse:
    result = await uc(
        LockRunCommand(
            workspace_id=auth.workspace_id,
            run_id=run_id,
            reason=body.reason,
        ),
        auth=auth,
    )
    return RunResponse.from_domain(result_to_response(result))


@router.post("/runs/{run_id}/unlock", response_model=RunResponse)
async def unlock_run(
    run_id: uuid.UUID,
    auth: AuthDep,
    body: UnlockRequest,
    uc: UnlockRunDep,
) -> RunResponse:
    result = await uc(
        UnlockRunCommand(
            workspace_id=auth.workspace_id,
            run_id=run_id,
            reason=body.reason,
        ),
        auth=auth,
    )
    return RunResponse.from_domain(result_to_response(result))
