"""GetDashboardStats query use case."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from returns.result import Result, Success

from cellar.application.auth import AuthContext, require_same_workspace
from cellar.application.shared.query import Query
from cellar.domain.shared.errors import DomainError


@dataclass(frozen=True)
class DashboardStats:
    total_compounds: int
    total_batches: int
    total_samples: int
    active_protocols: int
    total_runs: int


@dataclass(frozen=True, kw_only=True)
class GetDashboardStatsQuery(Query):
    workspace_id: uuid.UUID


@runtime_checkable
class DashboardStatsReader(Protocol):
    """Read-model protocol for dashboard aggregate counts."""

    async def get_stats(self, workspace_id: uuid.UUID) -> DashboardStats: ...


class GetDashboardStats:
    def __init__(self, reader: DashboardStatsReader) -> None:
        self._reader = reader

    async def __call__(
        self, input: GetDashboardStatsQuery, auth: AuthContext | None = None
    ) -> Result[DashboardStats, DomainError]:
        require_same_workspace(auth, input.workspace_id)
        stats = await self._reader.get_stats(input.workspace_id)
        return Success(stats)
