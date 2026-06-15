"""Read-model contract for the decomposition ``/rows`` endpoint.

A bounded SQL page over assignment rows joined to molecules. Sort is driven by a
list of ``DecompositionRowSort`` (molecule columns or R-group labels); ``filter``
mapping (AG-Grid filterModel) is deferred to Unit B. ``activity`` arrives in
Part 2 (activity projection), so it is not part of this contract yet.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from returns.result import Failure, Result, Success

from cellar.application.sar_analysis.repositories import RGroupDecompositionRunRepository
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.shared.errors import DomainError, NotFoundError


@dataclass(frozen=True)
class DecompositionRow:
    molecule_id: UUID
    smiles: str | None
    registration_number: str
    name: str
    rgroups: dict[str, str]
    molecular_weight: float | None
    logp: float | None
    tpsa: float | None
    activity: float | None = None


@dataclass(frozen=True)
class DecompositionRowSort:
    col: str
    direction: str  # "asc" | "desc"


class DecompositionRowReader(Protocol):
    async def fetch_rows(
        self,
        run_id: UUID,
        *,
        workspace_id: UUID,
        offset: int,
        limit: int,
        sort: list[DecompositionRowSort],
        projection_id: UUID | None = None,
    ) -> list[DecompositionRow]: ...

    async def count_rows(self, run_id: UUID, *, workspace_id: UUID) -> int: ...


@dataclass(frozen=True)
class FetchDecompositionRowsInput:
    run_id: UUID
    workspace_id: UUID
    offset: int
    limit: int
    sort: list[DecompositionRowSort]
    projection_id: UUID | None = None


@dataclass(frozen=True)
class FetchDecompositionRowsOutput:
    rows: list[DecompositionRow]
    total: int


class FetchDecompositionRows:
    def __init__(
        self,
        *,
        repository: RGroupDecompositionRunRepository,
        reader: DecompositionRowReader,
        uow: UnitOfWork,
    ) -> None:
        self._repo = repository
        self._reader = reader
        self._uow = uow

    async def execute(
        self, payload: FetchDecompositionRowsInput
    ) -> Result[FetchDecompositionRowsOutput, DomainError]:
        async with self._uow:
            run = await self._repo.find_by_id(payload.run_id, workspace_id=payload.workspace_id)
            if run is None:
                return Failure(NotFoundError("RGroupDecompositionRun", str(payload.run_id)))
            rows = await self._reader.fetch_rows(
                payload.run_id,
                workspace_id=payload.workspace_id,
                offset=payload.offset,
                limit=payload.limit,
                sort=payload.sort,
                projection_id=payload.projection_id,
            )
            total = await self._reader.count_rows(
                payload.run_id, workspace_id=payload.workspace_id
            )
        return Success(FetchDecompositionRowsOutput(rows=rows, total=total))
