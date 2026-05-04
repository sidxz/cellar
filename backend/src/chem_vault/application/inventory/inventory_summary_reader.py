"""Read-model protocol for inventory summary queries.

The concrete implementation lives in
``infrastructure.persistence.sqlalchemy.inventory.inventory_summary_reader``.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class ActivityRow:
    """Raw activity row from the read model."""

    operation_type: str
    entity_type: str
    entity_id: uuid.UUID
    started_at: datetime


@dataclass(frozen=True)
class InventorySummaryCounts:
    """Raw inventory summary counts from the read model."""

    low_stock_count: int
    expiring_soon_count: int
    pending_sample_requests: int
    pending_synthesis_requests: int
    recent_activity: list[ActivityRow]


@runtime_checkable
class InventorySummaryReader(Protocol):
    """Application-layer protocol for inventory summary read-model queries."""

    async def get_summary(
        self, workspace_id: uuid.UUID
    ) -> InventorySummaryCounts: ...
