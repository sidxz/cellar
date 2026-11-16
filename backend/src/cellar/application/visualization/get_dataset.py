"""GetVisualizationDataset — one flat dataset for the workbench."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Literal

from returns.result import Failure, Result, Success

from cellar.application.auth import AuthContext, require_same_workspace
from cellar.application.shared.query import Query
from cellar.application.visualization.dataset import Dataset, build_wells_dataset
from cellar.application.visualization.dataset_reader import RunInfo, VisualizationDatasetReader
from cellar.domain.shared.errors import DomainError, NotFoundError, ValidationError

# Provisional; Task 15's benchmark sets the final values.
MAX_DATASET_ROWS = 200_000
MAX_DATASET_COLUMNS = 400


@dataclass(frozen=True)
class ProtocolSource:
    protocol_id: uuid.UUID
    run_ids: tuple[uuid.UUID, ...] | None = None


@dataclass(frozen=True)
class RunSource:
    run_id: uuid.UUID


@dataclass(frozen=True, kw_only=True)
class GetVisualizationDatasetQuery(Query):
    workspace_id: uuid.UUID
    source: ProtocolSource | RunSource
    level: Literal["wells"]


class GetVisualizationDataset:
    def __init__(self, reader: VisualizationDatasetReader) -> None:
        self._reader = reader

    async def _resolve_runs(
        self, workspace_id: uuid.UUID, source: ProtocolSource | RunSource
    ) -> list[RunInfo] | NotFoundError:
        if isinstance(source, RunSource):
            runs = await self._reader.runs_by_ids(workspace_id, [source.run_id])
            return runs or NotFoundError("Run", str(source.run_id))
        runs = await self._reader.runs_for_protocol(workspace_id, source.protocol_id)
        if runs is None:
            return NotFoundError("Protocol", str(source.protocol_id))
        if source.run_ids is None:
            return runs
        by_id = {r.id: r for r in runs}
        missing = [rid for rid in source.run_ids if rid not in by_id]
        if missing:
            return NotFoundError("Run", str(missing[0]))
        return [by_id[rid] for rid in source.run_ids]

    async def __call__(
        self, input: GetVisualizationDatasetQuery, auth: AuthContext | None = None
    ) -> Result[Dataset, DomainError]:
        require_same_workspace(auth, input.workspace_id)
        ws = input.workspace_id

        runs = await self._resolve_runs(ws, input.source)
        if isinstance(runs, NotFoundError):
            return Failure(runs)
        run_ids = [r.id for r in runs]

        total = sum((await self._reader.count_wells_rows(ws, run_ids)).values())
        if total > MAX_DATASET_ROWS:
            return Failure(
                ValidationError(
                    f"This selection has {total:,} rows; the limit is {MAX_DATASET_ROWS:,}. "
                    "Choose fewer runs."
                )
            )

        defs = await self._reader.readout_definitions(ws, sorted({r.protocol_id for r in runs}))
        rows = await self._reader.fetch_well_values(ws, run_ids)
        dataset = build_wells_dataset(runs, defs, rows)
        if len(dataset.columns) > MAX_DATASET_COLUMNS:
            return Failure(
                ValidationError(
                    f"This selection has {len(dataset.columns):,} columns; the limit is "
                    f"{MAX_DATASET_COLUMNS:,}. Choose fewer runs."
                )
            )
        return Success(dataset)
