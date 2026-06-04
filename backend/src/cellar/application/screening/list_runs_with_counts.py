"""ListRunsWithCounts query — runs by protocol enriched with molecule counts."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Result, Success

from cellar.application.auth import AuthContext, require_workspace_role
from cellar.application.shared.query import Query
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.screening_assay.repository import ReadoutDataRepository, RunRepository
from cellar.domain.screening_assay.run import Run
from cellar.domain.shared.errors import DomainError


@dataclass(frozen=True, kw_only=True)
class ListRunsWithCountsQuery(Query):
    workspace_id: uuid.UUID
    protocol_id: uuid.UUID
    tags: list[uuid.UUID] | None = None
    tag_logic: str = "any"


@dataclass(frozen=True)
class RunWithCounts:
    run: Run
    molecule_count: int


class ListRunsWithCounts:
    """Return runs for a protocol with molecule counts per run."""

    def __init__(
        self,
        uow: UnitOfWork,
        run_repo: RunRepository,
        readout_data_repo: ReadoutDataRepository,
    ) -> None:
        self._uow = uow
        self._run_repo = run_repo
        self._rd_repo = readout_data_repo

    async def __call__(
        self,
        input: ListRunsWithCountsQuery,
        auth: AuthContext | None = None,
    ) -> Result[list[RunWithCounts], DomainError]:
        require_workspace_role(auth, "viewer")
        async with self._uow:
            runs = await self._run_repo.find_by_protocol(
                input.workspace_id,
                input.protocol_id,
                tags=input.tags,
                tag_logic=input.tag_logic,
            )
            counts = await self._rd_repo.get_molecule_counts(
                input.workspace_id, [r.id for r in runs]
            )
            return Success(
                [RunWithCounts(run=r, molecule_count=counts.get(r.id, 0)) for r in runs]
            )
