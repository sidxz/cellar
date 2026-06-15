"""SAR analysis HTTP routes — server-side R-group decomposition (async runs)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Response, status
from pydantic import BaseModel, Field

from cellar.application.sar_analysis.cancel_decomposition_run import (
    CancelDecompositionRunInput,
)
from cellar.application.sar_analysis.decomposition_rows import (
    DecompositionRow,
    DecompositionRowSort,
    FetchDecompositionRowsInput,
)
from cellar.application.sar_analysis.get_decomposition_run import GetDecompositionRunInput
from cellar.application.sar_analysis.start_decomposition_run import StartDecompositionRunInput
from cellar.application.shared.pagination import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE
from cellar.domain.sar_analysis.rgroup_decomposition_run import (
    RGroupDecompositionRun,
    RGroupDecompositionRunStatus,
)
from cellar.interface.dependencies import AuthDep
from cellar.interface.dependencies._sar_analysis import (
    CancelDecompositionRunDep,
    FetchDecompositionRowsDep,
    GetDecompositionRunDep,
    StartDecompositionRunDep,
)
from cellar.interface.error_handlers import result_to_response

router = APIRouter(prefix="/api/v1/sar", tags=["sar-analysis"])


class StartDecompositionRequest(BaseModel):
    molecule_ids: list[UUID] | None = None
    collection_id: UUID | None = None
    core_smiles: str


class DecompositionRunResponse(BaseModel):
    run_id: UUID
    status: str
    rgroup_labels: list[str]
    matched_count: int
    unmatched_count: int
    total_count: int
    error_message: str | None = None


class RowSortSpec(BaseModel):
    col: str
    dir: Literal["asc", "desc"] = "asc"


class DecompositionRowsRequest(BaseModel):
    offset: int = Field(default=0, ge=0)
    limit: int = Field(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE)
    sort: list[RowSortSpec] | None = None
    # Accepted for forward-compat; the AG-Grid filterModel mapping lands in Unit B.
    filter: dict[str, Any] | None = None


class DecompositionRowView(BaseModel):
    molecule_id: UUID
    smiles: str | None
    registration_number: str
    name: str
    rgroups: dict[str, str]
    mw: float | None
    clogp: float | None
    tpsa: float | None


class DecompositionRowsResponse(BaseModel):
    rows: list[DecompositionRowView]
    total: int


def _run_view(run: RGroupDecompositionRun) -> DecompositionRunResponse:
    return DecompositionRunResponse(
        run_id=run.id,
        status=run.status.value,
        rgroup_labels=list(run.rgroup_labels),
        matched_count=run.matched_count,
        unmatched_count=run.unmatched_count,
        total_count=run.total_count,
        error_message=run.error_message,
    )


def _row_view(row: DecompositionRow) -> DecompositionRowView:
    return DecompositionRowView(
        molecule_id=row.molecule_id,
        smiles=row.smiles,
        registration_number=row.registration_number,
        name=row.name,
        rgroups=row.rgroups,
        mw=row.molecular_weight,
        clogp=row.logp,
        tpsa=row.tpsa,
    )


@router.post("/decomposition", status_code=status.HTTP_200_OK)
async def start_decomposition(
    payload: StartDecompositionRequest,
    response: Response,
    auth: AuthDep,
    uc: StartDecompositionRunDep,
) -> DecompositionRunResponse:
    if (payload.molecule_ids is None) == (payload.collection_id is None):
        raise HTTPException(
            status_code=400,
            detail="exactly one of molecule_ids or collection_id must be set",
        )
    if not payload.core_smiles.strip():
        raise HTTPException(status_code=400, detail="core_smiles must not be empty")

    run = await uc.execute(
        StartDecompositionRunInput(
            workspace_id=auth.workspace_id,
            requested_by=auth.user_id,
            collection_id=payload.collection_id,
            molecule_ids=payload.molecule_ids,
            core_smiles=payload.core_smiles,
            now=datetime.now(UTC),
        )
    )
    if run.status != RGroupDecompositionRunStatus.READY:
        response.status_code = status.HTTP_202_ACCEPTED
    return _run_view(run)


@router.get("/decomposition/jobs/{run_id}")
async def get_decomposition_run(
    run_id: UUID,
    auth: AuthDep,
    uc: GetDecompositionRunDep,
) -> DecompositionRunResponse:
    run = result_to_response(
        await uc.execute(GetDecompositionRunInput(run_id=run_id, workspace_id=auth.workspace_id))
    )
    return _run_view(run)


@router.post("/decomposition/jobs/{run_id}/cancel")
async def cancel_decomposition_run(
    run_id: UUID,
    auth: AuthDep,
    uc: CancelDecompositionRunDep,
) -> DecompositionRunResponse:
    run = result_to_response(
        await uc.execute(
            CancelDecompositionRunInput(
                run_id=run_id, workspace_id=auth.workspace_id, now=datetime.now(UTC)
            )
        )
    )
    return _run_view(run)


@router.post("/decomposition/{run_id}/rows")
async def decomposition_rows(
    run_id: UUID,
    payload: DecompositionRowsRequest,
    auth: AuthDep,
    uc: FetchDecompositionRowsDep,
) -> DecompositionRowsResponse:
    sort = [DecompositionRowSort(col=s.col, direction=s.dir) for s in (payload.sort or [])]
    out = result_to_response(
        await uc.execute(
            FetchDecompositionRowsInput(
                run_id=run_id,
                workspace_id=auth.workspace_id,
                offset=payload.offset,
                limit=payload.limit,
                sort=sort,
            )
        )
    )
    return DecompositionRowsResponse(rows=[_row_view(r) for r in out.rows], total=out.total)
