"""GetProtocolStats query use case — dashboard metrics for a single protocol."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date

from returns.result import Failure, Result, Success

from chem_vault.application.auth import AuthContext
from chem_vault.application.screening.protocol_stats_reader import (
    ProtocolStatsReader,
)
from chem_vault.application.shared.query import Query
from chem_vault.domain.shared.errors import DomainError, NotFoundError


@dataclass(frozen=True, kw_only=True)
class GetProtocolStatsQuery(Query):
    workspace_id: uuid.UUID
    protocol_id: uuid.UUID


@dataclass(frozen=True)
class RunCounts:
    total: int
    draft: int
    in_progress: int
    completed: int
    approved: int
    rejected: int


@dataclass(frozen=True)
class LatestRunInfo:
    id: uuid.UUID
    run_date: date
    status: str
    plate_format: str | None
    plate_count: int
    compound_count: int
    z_prime: float | None


@dataclass(frozen=True)
class ProtocolStats:
    run_counts: RunCounts
    compound_count: int
    hit_count: int | None  # None if no criteria set
    hit_criteria_applied: bool
    latest_run: LatestRunInfo | None


class GetProtocolStats:
    """Return dashboard summary metrics for a single protocol.

    Delegates raw SA queries to ProtocolStatsReader (infrastructure).
    """

    def __init__(self, reader: ProtocolStatsReader) -> None:
        self._reader = reader

    async def __call__(
        self,
        input: GetProtocolStatsQuery,
        auth: AuthContext | None = None,
    ) -> Result[ProtocolStats, DomainError]:
        ws = input.workspace_id
        pid = input.protocol_id

        data = await self._reader.get_stats_data(ws, pid)

        # Business logic: protocol existence check
        if data.protocol is None:
            return Failure(
                NotFoundError(f"Protocol {pid} not found in workspace")
            )

        hit_criteria = data.protocol.recommended_hit_criteria
        hit_criteria_applied = bool(hit_criteria)

        run_counts = RunCounts(
            total=sum(data.status_counts.values()),
            draft=data.status_counts.get("draft", 0),
            in_progress=data.status_counts.get("in_progress", 0),
            completed=data.status_counts.get("completed", 0),
            approved=data.status_counts.get("approved", 0),
            rejected=data.status_counts.get("rejected", 0),
        )

        latest_run: LatestRunInfo | None = None
        if data.latest_run is not None:
            # Z-prime from qc_metrics JSONB
            z_prime: float | None = None
            qc_metrics = data.latest_run.qc_metrics
            if qc_metrics and isinstance(qc_metrics, dict):
                z_prime = qc_metrics.get("z_prime")

            latest_run = LatestRunInfo(
                id=data.latest_run.id,
                run_date=data.latest_run.run_date,
                status=data.latest_run.status,
                plate_format=data.latest_run.plate_format,
                plate_count=data.latest_run.plate_count,
                compound_count=data.latest_run.compound_count,
                z_prime=z_prime,
            )

        # hit_count: None for now (computed client-side)
        hit_count: int | None = None

        return Success(
            ProtocolStats(
                run_counts=run_counts,
                compound_count=data.compound_count,
                hit_count=hit_count,
                hit_criteria_applied=hit_criteria_applied,
                latest_run=latest_run,
            )
        )
