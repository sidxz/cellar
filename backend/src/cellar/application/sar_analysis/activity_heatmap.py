"""Read contract for the server-aggregated activity heatmap.

One ``GROUP BY (rgroups->>axis_y, rgroups->>axis_x)`` over assignment ⋈
activity_value, ``argmin(scalar)`` per cell. Argmin is correct because the FE
gates heatmap coloring/curve-expand to dose-response potency channels, where the
scalar is a concentration (lower = more potent = the right cell representative).
Each axis is capped to the top-K substituents by member count; ``y_total`` /
``x_total`` / ``truncated`` let the UI label "top K of N" honestly.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol
from uuid import UUID

from returns.result import Failure, Result, Success

from cellar.application.sar_analysis.repositories import (
    RGroupDecompositionRunRepository,
    SarActivityProjectionRepository,
)
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.shared.errors import DomainError, NotFoundError

HEATMAP_AXIS_TOP_K = 30


@dataclass(frozen=True)
class HeatmapCell:
    y: str
    x: str
    count: int
    best_scalar: float
    best_molecule_id: UUID
    best_molecule_label: str
    best_snapshot: dict[str, Any]


@dataclass(frozen=True)
class HeatmapResult:
    x_values: list[str]
    y_values: list[str]
    cells: list[HeatmapCell]
    y_total: int
    x_total: int
    truncated: bool


class ActivityHeatmapReader(Protocol):
    async def fetch_heatmap(
        self,
        run_id: UUID,
        *,
        workspace_id: UUID,
        projection_id: UUID,
        axis_y: str,
        axis_x: str,
        top_k: int = HEATMAP_AXIS_TOP_K,
    ) -> HeatmapResult: ...


@dataclass(frozen=True)
class FetchActivityHeatmapInput:
    run_id: UUID
    projection_id: UUID
    workspace_id: UUID
    axis_y: str
    axis_x: str


class FetchActivityHeatmap:
    def __init__(
        self,
        *,
        run_repository: RGroupDecompositionRunRepository,
        projection_repository: SarActivityProjectionRepository,
        reader: ActivityHeatmapReader,
        uow: UnitOfWork,
    ) -> None:
        self._runs = run_repository
        self._projections = projection_repository
        self._reader = reader
        self._uow = uow

    async def execute(
        self, payload: FetchActivityHeatmapInput
    ) -> Result[HeatmapResult, DomainError]:
        async with self._uow:
            run = await self._runs.find_by_id(payload.run_id, workspace_id=payload.workspace_id)
            if run is None:
                return Failure(NotFoundError("RGroupDecompositionRun", str(payload.run_id)))
            projection = await self._projections.find_by_id(
                payload.projection_id, workspace_id=payload.workspace_id
            )
            if projection is None:
                return Failure(NotFoundError("SarActivityProjection", str(payload.projection_id)))
            result = await self._reader.fetch_heatmap(
                payload.run_id,
                workspace_id=payload.workspace_id,
                projection_id=payload.projection_id,
                axis_y=payload.axis_y,
                axis_x=payload.axis_x,
            )
        return Success(result)
