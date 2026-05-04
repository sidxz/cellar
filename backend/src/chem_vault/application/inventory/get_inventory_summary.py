"""GetInventorySummary query use case — dashboard metrics for inventory hub."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime

from returns.result import Result, Success

from chem_vault.application.auth import AuthContext, require_same_workspace
from chem_vault.application.inventory.inventory_summary_reader import (
    InventorySummaryReader,
)
from chem_vault.application.shared.query import Query
from chem_vault.domain.shared.errors import DomainError


@dataclass(frozen=True, kw_only=True)
class GetInventorySummaryQuery(Query):
    workspace_id: uuid.UUID


@dataclass(frozen=True)
class ActivityItem:
    description: str
    entity_type: str
    entity_id: uuid.UUID
    occurred_at: datetime


@dataclass(frozen=True)
class InventorySummary:
    low_stock_count: int
    expiring_soon_count: int
    pending_requests_count: int
    recent_activity: list[ActivityItem] = field(default_factory=list)


class GetInventorySummary:
    """Return dashboard summary metrics for the inventory hub.

    Delegates raw SA queries to InventorySummaryReader (infrastructure).
    """

    def __init__(self, reader: InventorySummaryReader) -> None:
        self._reader = reader

    async def __call__(
        self,
        input: GetInventorySummaryQuery,
        auth: AuthContext | None = None,
    ) -> Result[InventorySummary, DomainError]:
        require_same_workspace(auth, input.workspace_id)

        data = await self._reader.get_summary(input.workspace_id)

        recent_activity = [
            ActivityItem(
                description=f"{row.operation_type.replace('_', ' ').capitalize()} {row.entity_type}",
                entity_type=row.entity_type,
                entity_id=row.entity_id,
                occurred_at=row.started_at,
            )
            for row in data.recent_activity
        ]

        return Success(
            InventorySummary(
                low_stock_count=data.low_stock_count,
                expiring_soon_count=data.expiring_soon_count,
                pending_requests_count=data.pending_sample_requests
                + data.pending_synthesis_requests,
                recent_activity=recent_activity,
            )
        )
