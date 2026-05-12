"""Dashboard statistics endpoint."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from cellar.application.dashboard.get_dashboard_stats import (
    GetDashboardStatsQuery,
)
from cellar.interface.dependencies import AuthDep, GetDashboardStatsDep
from cellar.interface.error_handlers import result_to_response

router = APIRouter(prefix="/api/v1/dashboard", tags=["dashboard"])


class DashboardStatsResponse(BaseModel):
    total_compounds: int
    total_batches: int
    total_samples: int
    active_protocols: int
    total_runs: int

    @classmethod
    def from_domain(cls, stats: object) -> DashboardStatsResponse:
        return cls(
            total_compounds=getattr(stats, "total_compounds", 0),
            total_batches=getattr(stats, "total_batches", 0),
            total_samples=getattr(stats, "total_samples", 0),
            active_protocols=getattr(stats, "active_protocols", 0),
            total_runs=getattr(stats, "total_runs", 0),
        )


@router.get("/stats", response_model=DashboardStatsResponse)
async def get_dashboard_stats(
    auth: AuthDep,
    uc: GetDashboardStatsDep,
) -> DashboardStatsResponse:
    """Aggregate counts for the dashboard."""
    query = GetDashboardStatsQuery(workspace_id=auth.workspace_id)
    stats = result_to_response(await uc(query, auth=auth))
    return DashboardStatsResponse.from_domain(stats)
