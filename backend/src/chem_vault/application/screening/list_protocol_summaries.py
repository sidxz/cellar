"""ListProtocolSummaries — lightweight rows for the protocol picker.

Returns one row per protocol in the workspace with run_count + last_run_date
joined in, plus the resolved target name. Sorted with most-recently-run
protocols first; never-run protocols come last.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date

from returns.result import Result, Success

from chem_vault.application.auth import AuthContext
from chem_vault.application.shared.query import Query
from chem_vault.application.shared.unit_of_work import UnitOfWork
from chem_vault.domain.screening_assay.repository import (
    ProtocolRepository,
    RunRepository,
    TargetRepository,
)
from chem_vault.domain.shared.errors import DomainError


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
    target_id: uuid.UUID | None
    target_name: str | None
    run_count: int
    last_run_date: date | None


class ListProtocolSummaries:
    """Return rich, picker-ready protocol rows scoped to the workspace."""

    def __init__(
        self,
        uow: UnitOfWork,
        protocol_repo: ProtocolRepository,
        target_repo: TargetRepository,
        run_repo: RunRepository,
    ) -> None:
        self._uow = uow
        self._protocol_repo = protocol_repo
        self._target_repo = target_repo
        self._run_repo = run_repo

    async def __call__(
        self,
        input: ListProtocolSummariesQuery,
        auth: AuthContext | None = None,
    ) -> Result[list[ProtocolSummary], DomainError]:
        async with self._uow:
            protocols = await self._protocol_repo.find_by_workspace(input.workspace_id)
            targets = await self._target_repo.find_by_workspace(input.workspace_id)
            stats = await self._run_repo.aggregate_stats_by_protocol(input.workspace_id)
            scoped_ids: set[uuid.UUID] | None = None
            if input.project_ids:
                scoped_ids = await self._protocol_repo.find_protocol_ids_in_projects(
                    input.workspace_id, list(input.project_ids)
                )

        target_name_by_id: dict[uuid.UUID, str] = {t.id: t.name for t in targets}

        summaries: list[ProtocolSummary] = []
        for p in protocols:
            if scoped_ids is not None and p.id not in scoped_ids:
                continue
            count, last = stats.get(p.id, (0, None))
            summaries.append(
                ProtocolSummary(
                    id=p.id,
                    name=p.name,
                    status=p.status.value,
                    protocol_type=p.protocol_type.value,
                    description=p.description,
                    target_id=p.target_id,
                    target_name=target_name_by_id.get(p.target_id) if p.target_id else None,
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
