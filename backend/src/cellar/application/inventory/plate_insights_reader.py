"""Read-model protocol for per-org plate-insights dashboard queries.

The concrete implementation lives in
``infrastructure.persistence.sqlalchemy.inventory.plate_insights_reader``.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class CountBucket:
    key: str
    count: int


@dataclass(frozen=True)
class LocationCount:
    location_id: uuid.UUID | None  # None = unassigned bucket
    name: str  # "Unassigned" for None
    count: int


@dataclass(frozen=True)
class GroupSize:
    group_id: uuid.UUID
    name: str
    count: int


@dataclass(frozen=True)
class WeeklyLoanActivity:
    week_start: date  # Monday (ISO), matches Postgres date_trunc('week')
    requested: int
    returned: int


@dataclass(frozen=True)
class PlateInsightsData:
    total_plates: int
    by_status: list[CountBucket]
    by_type: list[CountBucket]
    by_location: list[LocationCount]
    group_sizes: list[GroupSize]  # desc by count, ALL groups with >=1 plate
    loan_activity_weekly: list[WeeklyLoanActivity]  # exactly 12 zero-filled buckets, oldest first
    open_loans: int
    overdue_count: int


@runtime_checkable
class PlateInsightsReader(Protocol):
    """Application-layer protocol for per-org plate-insights read-model queries."""

    async def get_insights(
        self, workspace_id: uuid.UUID, org_id: uuid.UUID
    ) -> PlateInsightsData: ...
