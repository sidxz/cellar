"""Protocol hub API routes — protocol-level dashboard metrics."""

from __future__ import annotations

import uuid
from datetime import date

from fastapi import APIRouter
from pydantic import BaseModel

from chem_vault.application.screening.get_protocol_activity import (
    ActivitySummaryQuery,
)
from chem_vault.application.screening.get_protocol_stats import (
    ProtocolStatsQuery,
)
from chem_vault.interface.dependencies import (
    AuthDep,
    GetProtocolActivitySummaryDep,
    GetProtocolStatsDep,
)
from chem_vault.interface.error_handlers import result_to_response

router = APIRouter(prefix="/api/v1/protocols", tags=["protocol-hub"])


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class RunCountsResponse(BaseModel):
    total: int
    draft: int
    in_progress: int
    completed: int
    approved: int
    rejected: int


class LatestRunResponse(BaseModel):
    id: uuid.UUID
    run_date: date
    status: str
    plate_format: str | None = None
    plate_count: int
    compound_count: int
    z_prime: float | None = None


class ProtocolStatsResponse(BaseModel):
    run_counts: RunCountsResponse
    compound_count: int
    hit_count: int | None = None
    hit_criteria_applied: bool
    latest_run: LatestRunResponse | None = None


class ActivitySummaryItemResponse(BaseModel):
    molecule_id: uuid.UUID
    molecule_name: str
    molecule_registration_number: str
    best_value: float | None = None
    mean_value: float | None = None
    run_count: int
    min_value: float | None = None
    max_value: float | None = None
    curve_class: str | None = None
    last_tested: str | None = None


class ActivitySummaryResponse(BaseModel):
    items: list[ActivitySummaryItemResponse]
    readout_name: str
    readout_unit: str | None = None
    total_compounds: int


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/{protocol_id}/stats", response_model=ProtocolStatsResponse)
async def get_protocol_stats(
    protocol_id: uuid.UUID,
    auth: AuthDep,
    uc: GetProtocolStatsDep,
) -> ProtocolStatsResponse:
    """Dashboard metrics for a single protocol: run counts, compounds, latest run."""
    query = ProtocolStatsQuery(
        workspace_id=auth.workspace_id,
        protocol_id=protocol_id,
    )
    stats = result_to_response(await uc(query, auth=auth))
    latest_run = None
    if stats.latest_run is not None:
        latest_run = LatestRunResponse(
            id=stats.latest_run.id,
            run_date=stats.latest_run.run_date,
            status=stats.latest_run.status,
            plate_format=stats.latest_run.plate_format,
            plate_count=stats.latest_run.plate_count,
            compound_count=stats.latest_run.compound_count,
            z_prime=stats.latest_run.z_prime,
        )
    return ProtocolStatsResponse(
        run_counts=RunCountsResponse(
            total=stats.run_counts.total,
            draft=stats.run_counts.draft,
            in_progress=stats.run_counts.in_progress,
            completed=stats.run_counts.completed,
            approved=stats.run_counts.approved,
            rejected=stats.run_counts.rejected,
        ),
        compound_count=stats.compound_count,
        hit_count=stats.hit_count,
        hit_criteria_applied=stats.hit_criteria_applied,
        latest_run=latest_run,
    )


@router.get("/{protocol_id}/activity-summary", response_model=ActivitySummaryResponse)
async def get_protocol_activity_summary(
    protocol_id: uuid.UUID,
    auth: AuthDep,
    uc: GetProtocolActivitySummaryDep,
    readout_name: str | None = None,
) -> ActivitySummaryResponse:
    """Compound-centric results aggregated across all runs for a protocol."""
    query = ActivitySummaryQuery(
        workspace_id=auth.workspace_id,
        protocol_id=protocol_id,
        readout_name=readout_name,
    )
    summary = result_to_response(await uc(query, auth=auth))
    return ActivitySummaryResponse(
        items=[ActivitySummaryItemResponse(**vars(item)) for item in summary.items],
        readout_name=summary.readout_name,
        readout_unit=summary.readout_unit,
        total_compounds=summary.total_compounds,
    )
