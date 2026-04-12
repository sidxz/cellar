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
    GetCompoundCurvesDep,
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


class CurveParamsResponse(BaseModel):
    hill_slope: float
    top: float
    bottom: float
    fitted_value: float
    r_squared: float


class ReadoutValueResponse(BaseModel):
    best: float | None = None
    mean: float | None = None
    curve_class: str | None = None
    curve_params: CurveParamsResponse | None = None
    data_points: list[dict[str, float]] | None = None
    n: int | None = None
    sd: float | None = None


class ReadoutDefInfoResponse(BaseModel):
    name: str
    data_type: str
    unit: str | None = None
    best_direction: str


class CompoundActivityResponse(BaseModel):
    molecule_id: uuid.UUID
    molecule_name: str
    registration_number: str
    run_count: int
    last_tested: str | None = None
    smiles: str | None = None
    synonyms: list[str] = []
    readouts: dict[str, ReadoutValueResponse]


class ActivitySummaryV2Response(BaseModel):
    items: list[CompoundActivityResponse]
    readout_definitions: list[ReadoutDefInfoResponse]
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


@router.get("/{protocol_id}/activity-summary", response_model=ActivitySummaryV2Response)
async def get_protocol_activity_summary(
    protocol_id: uuid.UUID,
    auth: AuthDep,
    uc: GetProtocolActivitySummaryDep,
) -> ActivitySummaryV2Response:
    """Compound-centric results aggregated across all runs for a protocol."""
    query = ActivitySummaryQuery(
        workspace_id=auth.workspace_id,
        protocol_id=protocol_id,
    )
    summary = result_to_response(await uc(query, auth=auth))
    return ActivitySummaryV2Response(
        items=[
            CompoundActivityResponse(
                molecule_id=item.molecule_id,
                molecule_name=item.molecule_name,
                registration_number=item.registration_number,
                run_count=item.run_count,
                last_tested=item.last_tested,
                smiles=item.smiles,
                synonyms=item.synonyms,
                readouts={
                    name: ReadoutValueResponse(
                        best=rv.best,
                        mean=rv.mean,
                        curve_class=rv.curve_class,
                        curve_params=(
                            CurveParamsResponse(
                                hill_slope=rv.curve_params.hill_slope,
                                top=rv.curve_params.top,
                                bottom=rv.curve_params.bottom,
                                fitted_value=rv.curve_params.fitted_value,
                                r_squared=rv.curve_params.r_squared,
                            )
                            if rv.curve_params is not None
                            else None
                        ),
                        data_points=rv.data_points,
                        n=rv.n,
                        sd=rv.sd,
                    )
                    for name, rv in item.readouts.items()
                },
            )
            for item in summary.items
        ],
        readout_definitions=[
            ReadoutDefInfoResponse(
                name=rd.name,
                data_type=rd.data_type,
                unit=rd.unit,
                best_direction=rd.best_direction,
            )
            for rd in summary.readout_definitions
        ],
        total_compounds=summary.total_compounds,
    )


@router.get("/{protocol_id}/compounds/{molecule_id}/dose-response")
async def get_compound_dose_response(
    protocol_id: uuid.UUID,
    molecule_id: uuid.UUID,
    auth: AuthDep,
    uc: GetCompoundCurvesDep,
) -> list[dict]:
    """All dose-response curves for a compound in a protocol."""
    from chem_vault.application.screening.get_compound_curves import CompoundCurvesQuery

    query = CompoundCurvesQuery(
        workspace_id=auth.workspace_id,
        protocol_id=protocol_id,
        molecule_id=molecule_id,
    )
    return result_to_response(await uc(query, auth=auth))
