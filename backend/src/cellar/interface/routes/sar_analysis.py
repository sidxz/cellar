"""SAR analysis HTTP routes — server-side R-group decomposition (async runs)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Response, status
from pydantic import BaseModel, Field

from cellar.application.sar_analysis.activity_channel import ActivityChannelSpec
from cellar.application.sar_analysis.activity_heatmap import FetchActivityHeatmapInput
from cellar.application.sar_analysis.cancel_activity_projection import (
    CancelActivityProjectionInput,
)
from cellar.application.sar_analysis.cancel_decomposition_run import (
    CancelDecompositionRunInput,
)
from cellar.application.sar_analysis.decomposition_rows import (
    DecompositionRow,
    DecompositionRowSort,
    FetchDecompositionRowsInput,
)
from cellar.application.sar_analysis.get_activity_projection import GetActivityProjectionInput
from cellar.application.sar_analysis.get_decomposition_run import GetDecompositionRunInput
from cellar.application.sar_analysis.start_activity_projection import (
    StartActivityProjectionInput,
)
from cellar.application.sar_analysis.start_decomposition_run import StartDecompositionRunInput
from cellar.application.shared.pagination import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE
from cellar.domain.sar_analysis.rgroup_decomposition_run import (
    RGroupDecompositionRun,
    RGroupDecompositionRunStatus,
)
from cellar.domain.sar_analysis.sar_activity_projection import (
    SarActivityProjection,
    SarActivityProjectionStatus,
)
from cellar.domain.screening_assay.run_scope import (
    RunScope,  # noqa: F401  (documents run_scopes wire)
)
from cellar.domain.shared.aggregation_types import QualifierHandling, SelectionRule
from cellar.domain.shared.hit_criterion import InterceptKey
from cellar.interface.dependencies import AuthDep
from cellar.interface.dependencies._sar_analysis import (
    CancelActivityProjectionDep,
    CancelDecompositionRunDep,
    FetchActivityHeatmapDep,
    FetchDecompositionRowsDep,
    GetActivityProjectionDep,
    GetDecompositionRunDep,
    StartActivityProjectionDep,
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
    projection_id: UUID | None = None


class DecompositionRowView(BaseModel):
    molecule_id: UUID
    smiles: str | None
    registration_number: str
    name: str
    rgroups: dict[str, str]
    mw: float | None
    clogp: float | None
    tpsa: float | None
    activity: float | None = None


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
        activity=row.activity,
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
                projection_id=payload.projection_id,
            )
        )
    )
    return DecompositionRowsResponse(rows=[_row_view(r) for r in out.rows], total=out.total)


class InterceptKeyModel(BaseModel):
    kind: Literal["ec", "ic"]
    level: float


class ActivityChannelRequest(BaseModel):
    column: str
    source: Literal["dr_curve", "readout_data"]
    selection_rule: SelectionRule = SelectionRule.LATEST_APPROVED_RUN
    qualifier_handling: QualifierHandling = QualifierHandling.EXCLUDE_QUALIFIED
    intercept_key: InterceptKeyModel | None = None
    run_scopes: dict[str, Any] | None = None
    protocol_id: UUID | None = None
    label: str = ""


class StartActivityProjectionRequest(BaseModel):
    molecule_ids: list[UUID] | None = None
    collection_id: UUID | None = None
    channel: ActivityChannelRequest


class ActivityProjectionResponse(BaseModel):
    projection_id: UUID
    status: str
    value_count: int
    error_message: str | None = None


class HeatmapRequest(BaseModel):
    axis_y: str
    axis_x: str
    projection_id: UUID


class HeatmapCellView(BaseModel):
    y: str
    x: str
    count: int
    best_scalar: float
    best_molecule_id: UUID
    best_molecule_label: str
    best_snapshot: dict[str, Any]


class HeatmapResponse(BaseModel):
    x_values: list[str]
    y_values: list[str]
    cells: list[HeatmapCellView]
    y_total: int
    x_total: int
    truncated: bool


def _projection_view(p: SarActivityProjection) -> ActivityProjectionResponse:
    return ActivityProjectionResponse(
        projection_id=p.id,
        status=p.status.value,
        value_count=p.value_count,
        error_message=p.error_message,
    )


def _to_channel(req: ActivityChannelRequest) -> ActivityChannelSpec:
    return ActivityChannelSpec(
        column=req.column,
        source=req.source,
        selection_rule=req.selection_rule,
        qualifier_handling=req.qualifier_handling,
        intercept_key=(
            InterceptKey(kind=req.intercept_key.kind, level=req.intercept_key.level)
            if req.intercept_key is not None
            else None
        ),
        run_scopes=req.run_scopes,
        protocol_id=req.protocol_id,
        label=req.label,
    )


@router.post("/activity-projection", status_code=status.HTTP_200_OK)
async def start_activity_projection(
    payload: StartActivityProjectionRequest,
    response: Response,
    auth: AuthDep,
    uc: StartActivityProjectionDep,
) -> ActivityProjectionResponse:
    if (payload.molecule_ids is None) == (payload.collection_id is None):
        raise HTTPException(
            status_code=400,
            detail="exactly one of molecule_ids or collection_id must be set",
        )
    if not payload.channel.column.strip():
        raise HTTPException(status_code=400, detail="channel.column must not be empty")

    proj = await uc.execute(
        StartActivityProjectionInput(
            workspace_id=auth.workspace_id,
            requested_by=auth.user_id,
            collection_id=payload.collection_id,
            molecule_ids=payload.molecule_ids,
            channel=_to_channel(payload.channel),
            now=datetime.now(UTC),
        )
    )
    if proj.status != SarActivityProjectionStatus.READY:
        response.status_code = status.HTTP_202_ACCEPTED
    return _projection_view(proj)


@router.get("/activity-projection/jobs/{projection_id}")
async def get_activity_projection(
    projection_id: UUID,
    auth: AuthDep,
    uc: GetActivityProjectionDep,
) -> ActivityProjectionResponse:
    proj = result_to_response(
        await uc.execute(
            GetActivityProjectionInput(projection_id=projection_id, workspace_id=auth.workspace_id)
        )
    )
    return _projection_view(proj)


@router.post("/activity-projection/jobs/{projection_id}/cancel")
async def cancel_activity_projection(
    projection_id: UUID,
    auth: AuthDep,
    uc: CancelActivityProjectionDep,
) -> ActivityProjectionResponse:
    proj = result_to_response(
        await uc.execute(
            CancelActivityProjectionInput(
                projection_id=projection_id, workspace_id=auth.workspace_id, now=datetime.now(UTC)
            )
        )
    )
    return _projection_view(proj)


@router.post("/decomposition/{run_id}/heatmap")
async def decomposition_heatmap(
    run_id: UUID,
    payload: HeatmapRequest,
    auth: AuthDep,
    uc: FetchActivityHeatmapDep,
) -> HeatmapResponse:
    out = result_to_response(
        await uc.execute(
            FetchActivityHeatmapInput(
                run_id=run_id,
                projection_id=payload.projection_id,
                workspace_id=auth.workspace_id,
                axis_y=payload.axis_y,
                axis_x=payload.axis_x,
            )
        )
    )
    return HeatmapResponse(
        x_values=out.x_values,
        y_values=out.y_values,
        cells=[
            HeatmapCellView(
                y=c.y,
                x=c.x,
                count=c.count,
                best_scalar=c.best_scalar,
                best_molecule_id=c.best_molecule_id,
                best_molecule_label=c.best_molecule_label,
                best_snapshot=c.best_snapshot,
            )
            for c in out.cells
        ],
        y_total=out.y_total,
        x_total=out.x_total,
        truncated=out.truncated,
    )
