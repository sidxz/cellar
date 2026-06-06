"""ListProtocolSummaries — lightweight rows for the protocol picker.

Returns one row per protocol in the workspace with run_count + last_run_date
joined in, plus the protocol's effective targets (direct union run-derived). Sorted
with most-recently-run protocols first; never-run protocols come last.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date

from returns.result import Result, Success

from cellar.application.auth import AuthContext, require_same_workspace, require_workspace_role
from cellar.application.shared.query import Query
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.screening_assay.repository import (
    ProtocolRepository,
    RunRepository,
)
from cellar.domain.screening_assay.target import TargetRef
from cellar.domain.shared.errors import DomainError


@dataclass(frozen=True, kw_only=True)
class ListProtocolSummariesQuery(Query):
    workspace_id: uuid.UUID
    # When non-empty, restrict the summaries to protocols that are linked
    # to ANY of these projects (union scope for the search-panel picker).
    project_ids: tuple[uuid.UUID, ...] | None = None


@dataclass(frozen=True)
class ProtocolSummary:
    id: uuid.UUID
    name: str
    status: str
    protocol_type: str
    description: str | None
    targets: list[TargetRef] = field(default_factory=list)
    run_count: int = 0
    last_run_date: date | None = None


class ListProtocolSummaries:
    """Return rich, picker-ready protocol rows scoped to the workspace."""

    def __init__(
        self,
        uow: UnitOfWork,
        protocol_repo: ProtocolRepository,
        run_repo: RunRepository,
    ) -> None:
        self._uow = uow
        self._protocol_repo = protocol_repo
        self._run_repo = run_repo

    async def __call__(
        self,
        input: ListProtocolSummariesQuery,
        auth: AuthContext | None = None,
    ) -> Result[list[ProtocolSummary], DomainError]:
        require_workspace_role(auth, "viewer")
        require_same_workspace(auth, input.workspace_id)
        async with self._uow:
            protocols = await self._protocol_repo.find_by_workspace(input.workspace_id)
            stats = await self._run_repo.aggregate_stats_by_protocol(input.workspace_id)
            scoped_ids: set[uuid.UUID] | None = None
            if input.project_ids:
                scoped_ids = await self._protocol_repo.find_protocol_ids_in_projects(
                    input.workspace_id, list(input.project_ids)
                )

            visible = [p for p in protocols if scoped_ids is None or p.id in scoped_ids]
            targets_by_protocol = await self._protocol_repo.find_effective_targets_for_protocols(
                input.workspace_id, [p.id for p in visible]
            )

        summaries: list[ProtocolSummary] = []
        for p in visible:
            count, last = stats.get(p.id, (0, None))
            summaries.append(
                ProtocolSummary(
                    id=p.id,
                    name=p.name,
                    status=p.status.value,
                    protocol_type=p.protocol_type.value,
                    description=p.description,
                    targets=targets_by_protocol.get(p.id, []),
                    run_count=count,
                    last_run_date=last,
                )
            )

        # Most-recently-run first; never-run protocols sink to the bottom but
        # remain alphabetical among themselves to keep the list deterministic.
        summaries.sort(
            key=lambda s: (
                s.last_run_date is None,
                -(s.last_run_date.toordinal() if s.last_run_date else 0),
                s.name.lower(),
            )
        )
        return Success(summaries)
