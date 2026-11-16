"""GetVisualizationDataset — one flat dataset for the workbench."""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass
from typing import Literal

from returns.result import Failure, Result, Success

from cellar.application.auth import AuthContext, require_same_workspace
from cellar.application.screening.compound_curves_reader import CurveRow
from cellar.application.screening.get_protocol_activity import VALID_STATUSES
from cellar.application.screening.protocol_activity_reader import (
    AggregateScope,
    DRAggRow,
    NumericReadoutRow,
    ProtocolActivityReader,
)
from cellar.application.shared.query import Query
from cellar.application.visualization.aggregated_dataset import (
    AggLevel,
    build_aggregated_dataset,
)
from cellar.application.visualization.dataset import Dataset, build_wells_dataset
from cellar.application.visualization.dataset_reader import RunInfo, VisualizationDatasetReader
from cellar.domain.shared.errors import DomainError, NotFoundError, ValidationError

# From the stage-1 benchmark (384-well plates, raw + one normalized layer): 100k rows
# build and serialize in about 1.8 s, 200k in about 3.4 s. Cost follows readout values
# (rows x value columns); the column cap guards payload size, not latency.
MAX_DATASET_ROWS = 100_000
MAX_DATASET_COLUMNS = 400

DatasetLevel = Literal["wells", "runs", "batches", "compounds"]


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
    level: DatasetLevel


def _too_many_rows(total: int) -> ValidationError:
    return ValidationError(
        f"This selection has {total:,} rows; the limit is {MAX_DATASET_ROWS:,}. Choose fewer runs."
    )


class GetVisualizationDataset:
    def __init__(
        self, reader: VisualizationDatasetReader, activity_reader: ProtocolActivityReader
    ) -> None:
        self._reader = reader
        self._activity_reader = activity_reader

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
        run_ids = list(dict.fromkeys(source.run_ids))
        missing = [rid for rid in run_ids if rid not in by_id]
        if missing:
            return NotFoundError("Run", str(missing[0]))
        return [by_id[rid] for rid in run_ids]

    async def __call__(
        self, input: GetVisualizationDatasetQuery, auth: AuthContext | None = None
    ) -> Result[Dataset, DomainError]:
        require_same_workspace(auth, input.workspace_id)
        ws = input.workspace_id

        runs = await self._resolve_runs(ws, input.source)
        if isinstance(runs, NotFoundError):
            return Failure(runs)
        if input.level == "wells":
            dataset = await self._wells(ws, runs)
        else:
            # A source reads one protocol: the protocol itself, or the run's.
            src = input.source
            protocol_id = (
                src.protocol_id if isinstance(src, ProtocolSource) else runs[0].protocol_id
            )
            dataset = await self._aggregated(ws, protocol_id, runs, input.level)
        if isinstance(dataset, ValidationError):
            return Failure(dataset)
        if len(dataset.columns) > MAX_DATASET_COLUMNS:
            return Failure(
                ValidationError(
                    f"This selection has {len(dataset.columns):,} columns; the limit is "
                    f"{MAX_DATASET_COLUMNS:,}. Choose fewer runs."
                )
            )
        return Success(dataset)

    async def _wells(self, ws: uuid.UUID, runs: list[RunInfo]) -> Dataset | ValidationError:
        run_ids = [r.id for r in runs]
        total = sum((await self._reader.count_wells_rows(ws, run_ids)).values())
        if total > MAX_DATASET_ROWS:
            return _too_many_rows(total)  # refused before loading anything

        defs = await self._reader.readout_definitions(ws, sorted({r.protocol_id for r in runs}))
        rows = await self._reader.fetch_well_values(ws, run_ids)
        molecules = await self._reader.compound_info(
            ws, list({r.molecule_id for r in rows if r.molecule_id is not None})
        )
        # About 1 s of pure CPU at the row cap: keep it off the event loop.
        return await asyncio.to_thread(build_wells_dataset, runs, defs, rows, molecules)

    async def _aggregated(
        self, ws: uuid.UUID, protocol_id: uuid.UUID, runs: list[RunInfo], level: AggLevel
    ) -> Dataset | ValidationError:
        """Runs show every run status; Batches and Compounds only the valid ones (as
        the Activity tab), one column per condition set."""
        run_ids = tuple(r.id for r in runs)
        scope = (
            AggregateScope(statuses=None, run_ids=run_ids, grain="run")
            if level == "runs"
            else AggregateScope(
                VALID_STATUSES,
                run_ids,
                "batch" if level == "batches" else "compound",
                by_conditions=True,
            )
        )
        aggregates = await self._activity_reader.get_aggregates(ws, protocol_id, scope)
        curves = await self._reader.fetch_curves(ws, list(run_ids)) if level == "runs" else []
        records: list[NumericReadoutRow | DRAggRow | CurveRow] = [
            *aggregates.numeric_rows,
            *aggregates.dr_agg_rows,
            *curves,
        ]
        defs = await self._reader.readout_definitions(ws, [protocol_id])
        molecules = await self._reader.compound_info(ws, list({r.molecule_id for r in records}))
        batches = await self._reader.batch_numbers(
            ws, list({r.batch_id for r in records if r.batch_id is not None})
        )
        dataset = await asyncio.to_thread(
            build_aggregated_dataset, level, runs, defs, aggregates, curves, molecules, batches
        )
        if len(dataset.row_ids) > MAX_DATASET_ROWS:
            return _too_many_rows(len(dataset.row_ids))
        return dataset
