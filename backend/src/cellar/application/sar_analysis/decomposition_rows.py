"""Read-model contract for the decomposition ``/rows`` endpoint.

A bounded SQL page over assignment rows joined to molecules. Sort is driven by a
list of ``DecompositionRowSort`` (molecule columns or R-group labels); ``filter``
mapping (AG-Grid filterModel) is deferred to Unit B. ``activity`` arrives in
Part 2 (activity projection), so it is not part of this contract yet.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol
from uuid import UUID

from returns.result import Failure, Result, Success

from cellar.application.sar_analysis.repositories import (
    RGroupDecompositionRunRepository,
    SarActivityProjectionRepository,
)
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
    activity_snapshot: dict[str, Any] | None = None


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
        filter: dict[str, Any] | None = None,
    ) -> list[DecompositionRow]: ...

    async def count_rows(
        self,
        run_id: UUID,
        *,
        workspace_id: UUID,
        projection_id: UUID | None = None,
        filter: dict[str, Any] | None = None,
    ) -> int: ...

    async def fetch_matched_ids(
        self,
        run_id: UUID,
        *,
        workspace_id: UUID,
        projection_id: UUID | None = None,
        filter: dict[str, Any] | None = None,
    ) -> list[UUID]: ...

    async def activity_reference(
        self,
        run_id: UUID,
        *,
        workspace_id: UUID,
        projection_id: UUID | None,
        filter: dict[str, Any] | None = None,
    ) -> float | None: ...


@dataclass(frozen=True)
class FetchDecompositionRowsInput:
    run_id: UUID
    workspace_id: UUID
    offset: int
    limit: int
    sort: list[DecompositionRowSort]
    projection_id: UUID | None = None
    filter: dict[str, Any] | None = None


@dataclass(frozen=True)
class FetchDecompositionRowsOutput:
    rows: list[DecompositionRow]
    # total / activity_reference are computed only on the first block (offset 0) —
    # the full-scan COUNT + MIN are invariant across scroll blocks of one
    # (run, projection, filter), and AG-Grid refetches block 0 whenever sort or
    # filter changes. They are None on later blocks; the client caches them.
    total: int | None = None
    activity_reference: float | None = None


class FetchDecompositionRows:
    def __init__(
        self,
        *,
        repository: RGroupDecompositionRunRepository,
        projection_repository: SarActivityProjectionRepository,
        reader: DecompositionRowReader,
        uow: UnitOfWork,
    ) -> None:
        self._repo = repository
        self._projections = projection_repository
        self._reader = reader
        self._uow = uow

    async def execute(
        self, payload: FetchDecompositionRowsInput
    ) -> Result[FetchDecompositionRowsOutput, DomainError]:
        async with self._uow:
            run = await self._repo.find_by_id(payload.run_id, workspace_id=payload.workspace_id)
            if run is None:
                return Failure(NotFoundError("RGroupDecompositionRun", str(payload.run_id)))
            # Validate projection ownership explicitly (mirrors the heatmap use
            # case) so the activity LEFT JOIN never depends on the implicit
            # molecule-UUID-disjointness invariant to stay tenant-safe.
            if payload.projection_id is not None:
                projection = await self._projections.find_by_id(
                    payload.projection_id, workspace_id=payload.workspace_id
                )
                if projection is None:
                    return Failure(
                        NotFoundError("SarActivityProjection", str(payload.projection_id))
                    )
            rows = await self._reader.fetch_rows(
                payload.run_id,
                workspace_id=payload.workspace_id,
                offset=payload.offset,
                limit=payload.limit,
                sort=payload.sort,
                projection_id=payload.projection_id,
                filter=payload.filter,
            )
            # The COUNT + MIN scans are invariant across scroll blocks of one
            # (run, projection, filter), so compute them once on the first block;
            # the client caches them for subsequent blocks. AG-Grid refetches
            # block 0 on any sort/filter change, so the cache stays correct.
            total: int | None = None
            reference: float | None = None
            if payload.offset == 0:
                total = await self._reader.count_rows(
                    payload.run_id,
                    workspace_id=payload.workspace_id,
                    projection_id=payload.projection_id,
                    filter=payload.filter,
                )
                if payload.projection_id is not None:
                    reference = await self._reader.activity_reference(
                        payload.run_id,
                        workspace_id=payload.workspace_id,
                        projection_id=payload.projection_id,
                        filter=payload.filter,
                    )
        return Success(
            FetchDecompositionRowsOutput(rows=rows, total=total, activity_reference=reference)
        )
