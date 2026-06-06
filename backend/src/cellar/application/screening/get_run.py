"""GetRun and ListRunsByProtocol query use cases.

``GetRun`` resolves the run's target refs inside the SAME unit of work as
the primary read, so a response never mixes two snapshots.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from returns.result import Failure, Result, Success

from cellar.application.auth import AuthContext, require_same_workspace, require_workspace_role
from cellar.application.shared.query import Query
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.screening_assay.repository import RunRepository
from cellar.domain.screening_assay.run import Run
from cellar.domain.screening_assay.target import TargetRef
from cellar.domain.shared.errors import DomainError, NotFoundError


@dataclass(frozen=True, kw_only=True)
class GetRunQuery(Query):
    workspace_id: uuid.UUID
    run_id: uuid.UUID


@dataclass(frozen=True, kw_only=True)
class ListRunsByProtocolQuery(Query):
    workspace_id: uuid.UUID
    protocol_id: uuid.UUID


@dataclass(frozen=True)
class RunWithTargets:
    """A run plus its target refs, read in one transaction."""

    run: Run
    targets: list[TargetRef] = field(default_factory=list)


class GetRun:
    def __init__(self, uow: UnitOfWork, repo: RunRepository) -> None:
        self._uow = uow
        self._repo = repo

    async def __call__(
        self, input: GetRunQuery, auth: AuthContext | None = None
    ) -> Result[RunWithTargets, DomainError]:
        require_workspace_role(auth, "viewer")
        require_same_workspace(auth, input.workspace_id)
        async with self._uow:
            run = await self._repo.find_by_id_in_workspace(input.workspace_id, input.run_id)
            if run is None:
                return Failure(NotFoundError("Run", str(input.run_id)))
            targets = await self._repo.find_target_refs_for_runs(input.workspace_id, [run.id])
            return Success(RunWithTargets(run=run, targets=targets.get(run.id, [])))


class ListRunsByProtocol:
    def __init__(self, uow: UnitOfWork, repo: RunRepository) -> None:
        self._uow = uow
        self._repo = repo

    async def __call__(
        self,
        input: ListRunsByProtocolQuery,
        auth: AuthContext | None = None,
    ) -> Result[list[Run], DomainError]:
        require_workspace_role(auth, "viewer")
        require_same_workspace(auth, input.workspace_id)
        async with self._uow:
            runs = await self._repo.find_by_protocol(input.workspace_id, input.protocol_id)
            return Success(runs)
