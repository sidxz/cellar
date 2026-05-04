"""Read-model protocol for protocol stats queries.

The concrete implementation lives in
``infrastructure.persistence.sqlalchemy.screening_assay.protocol_stats_reader``.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date
from typing import Any, Protocol, runtime_checkable


@dataclass(frozen=True)
class ProtocolStatsRow:
    """Minimal protocol info for the stats query."""

    id: uuid.UUID
    recommended_hit_criteria: Any | None


@dataclass(frozen=True)
class LatestRunRow:
    """Raw latest-run data from the read model."""

    id: uuid.UUID
    run_date: date
    status: str
    plate_format: str | None
    qc_metrics: dict | None
    plate_count: int
    compound_count: int


@dataclass(frozen=True)
class ProtocolStatsData:
    """All raw data needed to build the protocol stats."""

    protocol: ProtocolStatsRow | None
    status_counts: dict[str, int]
    compound_count: int
    latest_run: LatestRunRow | None


@runtime_checkable
class ProtocolStatsReader(Protocol):
    """Application-layer protocol for protocol stats read-model queries."""

    async def get_stats_data(
        self, workspace_id: uuid.UUID, protocol_id: uuid.UUID
    ) -> ProtocolStatsData: ...
