"""Run API routes."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any, Literal

from fastapi import APIRouter, Query, Response
from pydantic import BaseModel

from cellar.application.screening.create_run import CreateRunCommand
from cellar.application.screening.delete_run import DeleteRunCommand
from cellar.application.screening.get_run import GetRunQuery
from cellar.application.screening.list_runs_with_counts import (
    ListRunsWithCountsQuery,
)
from cellar.application.screening.lock_run import (
    LockRunCommand,
    UnlockRunCommand,
)
from cellar.application.screening.manage_run import (
    ApproveRunCommand,
    CompleteRunCommand,
    RejectRunCommand,
    StartRunCommand,
)
from cellar.application.screening.manage_run_targets import (
    AddRunTargetCommand,
    RemoveRunTargetCommand,
)
from cellar.application.screening.reset_run_data import (
    ResetRunDataCommand,
)
from cellar.application.screening.resolve_target_links import ResolveRunTargetsQuery
from cellar.application.screening.update_run import UpdateRunCommand
from cellar.application.shared.sentinel import UNSET
from cellar.domain.screening_assay.run import Run
from cellar.interface.dependencies import (
    AddRunTargetDep,
    ApproveRunDep,
    AuthDep,
    CompleteRunDep,
    CreateRunDep,
    DeleteRunDep,
    GetRunDep,
    ListRunsWithCountsDep,
    LockRunDep,
    RejectRunDep,
    RemoveRunTargetDep,
    ResetRunDataDep,
    ResolveRunTargetsDep,
    StartRunDep,
    UnlockRunDep,
    UpdateRunDep,
)
from cellar.interface.error_handlers import result_to_response
from cellar.interface.routes._target_refs import TargetRefResponse

router = APIRouter(prefix="/api/v1", tags=["runs"])


async def _run_targets(targets_uc: Any, auth: Any, run_id: uuid.UUID) -> list[TargetRefResponse]:
    """Resolve a single run's target refs for a response."""
    result = await targets_uc(
        ResolveRunTargetsQuery(workspace_id=auth.workspace_id, run_ids=(run_id,)),
        auth=auth,
    )
    refs = result_to_response(result).get(run_id, [])
    return [TargetRefResponse.from_ref(t) for t in refs]


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class RunResponse(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    protocol_id: uuid.UUID
    run_date: date
    created_at: datetime
    operator: uuid.UUID
    status: str
    is_locked: bool
    locked_by: uuid.UUID | None = None
    lock_reason: str | None = None
    qc_metrics: dict[str, Any] | None = None
    notes: str | None = None
    plate_count: int
    plate_barcodes: list[str] = []
    molecule_count: int = 0
    performed_at_org_id: uuid.UUID | None = None
    parent_run_id: uuid.UUID | None = None
    run_relationship_type: str | None = None
    plate_format: str | None = None
    plate_template_id: uuid.UUID | None = None
    conditions: dict[str, Any] | None = None
    targets: list[TargetRefResponse] = []

    @classmethod
    def from_domain(
        cls,
        r: Run,
        *,
        molecule_count: int = 0,
        targets: list[TargetRefResponse] | None = None,
    ) -> RunResponse:
        plate_barcodes = [p.barcode.value for p in r.plates if getattr(p, "barcode", None)]
        return cls(
            id=r.id,
            workspace_id=r.workspace_id,
            protocol_id=r.protocol_id,
            run_date=r.run_date,
            created_at=r.created_at,
            operator=r.operator,
            status=r.status.value,
            is_locked=r.is_locked,
            locked_by=r.locked_by,
            lock_reason=r.lock_reason,
            qc_metrics=r.qc_metrics,
            notes=r.notes,
            plate_count=len(r.plates),
            plate_barcodes=plate_barcodes,
            molecule_count=molecule_count,
            performed_at_org_id=r.performed_at_org_id,
            parent_run_id=r.parent_run_id,
            run_relationship_type=r.run_relationship_type.value
            if r.run_relationship_type
            else None,
            plate_format=r.plate_format.value if r.plate_format else None,
            plate_template_id=r.plate_template_id,
            conditions=r.conditions,
            targets=targets or [],
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
    target_ids: list[uuid.UUID] = []
    collection_ids: list[uuid.UUID] = []


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
    targets_uc: ResolveRunTargetsDep,
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
        target_ids=body.target_ids,
        collection_ids=body.collection_ids,
    )
    result = await uc(cmd, auth=auth)
    run = result_to_response(result)
    return RunResponse.from_domain(run, targets=await _run_targets(targets_uc, auth, run.id))


@router.get("/protocols/{protocol_id}/runs", response_model=list[RunResponse])
async def list_runs_by_protocol(
    protocol_id: uuid.UUID,
    auth: AuthDep,
    uc: ListRunsWithCountsDep,
    tags: list[uuid.UUID] | None = Query(default=None),
    tag_logic: Literal["any", "all"] = Query(default="any"),
) -> list[RunResponse]:
    result = await uc(
        ListRunsWithCountsQuery(
            workspace_id=auth.workspace_id,
            protocol_id=protocol_id,
            tags=tags,
            tag_logic=tag_logic,
        ),
        auth=auth,
    )
    # Targets ride along from the use case — same transaction as the rows.
    return [
        RunResponse.from_domain(
            item.run,
            molecule_count=item.molecule_count,
            targets=[TargetRefResponse.from_ref(t) for t in item.targets],
        )
        for item in result_to_response(result)
    ]


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
    item = result_to_response(result)
    return RunResponse.from_domain(
        item.run,
        targets=[TargetRefResponse.from_ref(t) for t in item.targets],
    )


@router.patch("/runs/{run_id}", response_model=RunResponse)
async def update_run(
    run_id: uuid.UUID,
    body: UpdateRunRequest,
    auth: AuthDep,
    targets_uc: ResolveRunTargetsDep,
    uc: UpdateRunDep,
) -> RunResponse:

    cmd = UpdateRunCommand(
        workspace_id=auth.workspace_id,
        run_id=run_id,
        qc_metrics=body.qc_metrics if "qc_metrics" in body.model_fields_set else UNSET,
        notes=body.notes if "notes" in body.model_fields_set else UNSET,
    )
    result = await uc(cmd, auth=auth)
    run = result_to_response(result)
    return RunResponse.from_domain(run, targets=await _run_targets(targets_uc, auth, run.id))


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
    targets_uc: ResolveRunTargetsDep,
    uc: StartRunDep,
) -> RunResponse:
    result = await uc(StartRunCommand(workspace_id=auth.workspace_id, run_id=run_id), auth=auth)
    run = result_to_response(result)
    return RunResponse.from_domain(run, targets=await _run_targets(targets_uc, auth, run.id))


@router.post("/runs/{run_id}/complete", response_model=RunResponse)
async def complete_run(
    run_id: uuid.UUID,
    auth: AuthDep,
    targets_uc: ResolveRunTargetsDep,
    body: CompleteRunRequest,
    uc: CompleteRunDep,
) -> RunResponse:
    result = await uc(
        CompleteRunCommand(
            workspace_id=auth.workspace_id,
            run_id=run_id,
            plate_count=body.plate_count,
            data_point_count=body.data_point_count,
        ),
        auth=auth,
    )
    run = result_to_response(result)
    return RunResponse.from_domain(run, targets=await _run_targets(targets_uc, auth, run.id))


@router.post("/runs/{run_id}/approve", response_model=RunResponse)
async def approve_run(
    run_id: uuid.UUID,
    auth: AuthDep,
    targets_uc: ResolveRunTargetsDep,
    uc: ApproveRunDep,
) -> RunResponse:
    result = await uc(ApproveRunCommand(workspace_id=auth.workspace_id, run_id=run_id), auth=auth)
    run = result_to_response(result)
    return RunResponse.from_domain(run, targets=await _run_targets(targets_uc, auth, run.id))


@router.post("/runs/{run_id}/reject", response_model=RunResponse)
async def reject_run(
    run_id: uuid.UUID,
    auth: AuthDep,
    targets_uc: ResolveRunTargetsDep,
    body: RejectRequest,
    uc: RejectRunDep,
) -> RunResponse:
    result = await uc(
        RejectRunCommand(workspace_id=auth.workspace_id, run_id=run_id, reason=body.reason),
        auth=auth,
    )
    run = result_to_response(result)
    return RunResponse.from_domain(run, targets=await _run_targets(targets_uc, auth, run.id))


@router.post("/runs/{run_id}/lock", response_model=RunResponse)
async def lock_run(
    run_id: uuid.UUID,
    auth: AuthDep,
    targets_uc: ResolveRunTargetsDep,
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
    run = result_to_response(result)
    return RunResponse.from_domain(run, targets=await _run_targets(targets_uc, auth, run.id))


@router.post("/runs/{run_id}/unlock", response_model=RunResponse)
async def unlock_run(
    run_id: uuid.UUID,
    auth: AuthDep,
    targets_uc: ResolveRunTargetsDep,
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
    run = result_to_response(result)
    return RunResponse.from_domain(run, targets=await _run_targets(targets_uc, auth, run.id))


# ---------------------------------------------------------------------------
# Run-Target association routes
# ---------------------------------------------------------------------------


@router.post("/runs/{run_id}/targets/{target_id}", status_code=204)
async def add_run_target(
    run_id: uuid.UUID,
    target_id: uuid.UUID,
    auth: AuthDep,
    uc: AddRunTargetDep,
) -> Response:
    """Attach a target to a run (idempotent). Rolls up to the run's protocol."""
    result = await uc(
        AddRunTargetCommand(workspace_id=auth.workspace_id, run_id=run_id, target_id=target_id),
        auth=auth,
    )
    result_to_response(result)
    return Response(status_code=204)


@router.delete("/runs/{run_id}/targets/{target_id}", status_code=204)
async def remove_run_target(
    run_id: uuid.UUID,
    target_id: uuid.UUID,
    auth: AuthDep,
    uc: RemoveRunTargetDep,
) -> Response:
    """Remove a target from a run. Auto-prunes the protocol if it was inherited-only."""
    result = await uc(
        RemoveRunTargetCommand(workspace_id=auth.workspace_id, run_id=run_id, target_id=target_id),
        auth=auth,
    )
    result_to_response(result)
    return Response(status_code=204)
