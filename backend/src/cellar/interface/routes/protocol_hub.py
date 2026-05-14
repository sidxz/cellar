"""Protocol hub API routes — protocol-level dashboard metrics."""

from __future__ import annotations

import uuid
from datetime import date

from fastapi import APIRouter
from pydantic import BaseModel

from cellar.application.screening.get_protocol_activity import (
    GetProtocolActivityQuery,
)
from cellar.application.screening.get_protocol_stats import (
    GetProtocolStatsQuery,
)
from cellar.interface.dependencies import (
    AuthDep,
    GetCompoundCurvesDep,
    GetProtocolActivitySummaryDep,
    GetProtocolStatsDep,
)
from cellar.interface.error_handlers import result_to_response

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


class InterceptSpecResponse(BaseModel):
    kind: str  # "ic" | "ec"
    level: float
    basis: str  # "relative_percent" | "absolute"
    label: str | None = None


class InterceptValueResponse(BaseModel):
    spec: InterceptSpecResponse
    value: float
    confidence_interval_low: float | None = None
    confidence_interval_high: float | None = None
    at_bound: bool = False


class CurveParamsResponse(BaseModel):
    hill_slope: float
    top: float
    bottom: float
    fitted_value: float
    r_squared: float
    # Per-spec intercepts (EC50, EC90, IC10, ...). Empty list on legacy
    # curves; the FE uses this to render one column per intercept on the
    # activity grid.
    intercept_values: list[InterceptValueResponse] = []


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
    # For DR readouts, the protocol's declared intercept specs. Drives
    # the activity grid's dynamic column headers (one column per spec).
    intercepts: list[InterceptSpecResponse] = []


class CompoundActivityResponse(BaseModel):
    molecule_id: uuid.UUID
    molecule_name: str
    registration_number: str
    run_count: int
    last_tested: str | None = None
    smiles: str | None = None
    batch_number: str | None = None
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
    query = GetProtocolStatsQuery(
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
    query = GetProtocolActivityQuery(
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
                batch_number=item.batch_number,
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
                                intercept_values=[
                                    InterceptValueResponse(
                                        spec=InterceptSpecResponse(
                                            kind=iv.spec.kind,
                                            level=iv.spec.level,
                                            basis=iv.spec.basis,
                                            label=iv.spec.label,
                                        ),
                                        value=iv.value,
                                        confidence_interval_low=iv.confidence_interval_low,
                                        confidence_interval_high=iv.confidence_interval_high,
                                        at_bound=iv.at_bound,
                                    )
                                    for iv in rv.curve_params.intercept_values
                                ],
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
                intercepts=[
                    InterceptSpecResponse(
                        kind=spec.kind,
                        level=spec.level,
                        basis=spec.basis,
                        label=spec.label,
                    )
                    for spec in rd.intercepts
                ],
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
    from cellar.application.screening.get_compound_curves import GetCompoundCurvesQuery

    query = GetCompoundCurvesQuery(
        workspace_id=auth.workspace_id,
        protocol_id=protocol_id,
        molecule_id=molecule_id,
    )
    return result_to_response(await uc(query, auth=auth))
