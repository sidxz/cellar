"""GetVisualizationDataset — one flat dataset for the workbench."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Sequence
from dataclasses import dataclass, replace
from typing import Literal

from returns.result import Failure, Result, Success

from cellar.application.auth import AuthContext, require_same_workspace
from cellar.application.screening.compound_curves_reader import CurveRow
from cellar.application.screening.get_protocol_activity import VALID_STATUSES
from cellar.application.screening.protocol_activity_reader import (
    ActivityAggregates,
    AggregateScope,
    DRAggRow,
    NumericReadoutRow,
    ProtocolActivityReader,
)
from cellar.application.shared.query import Query
from cellar.application.visualization.aggregated_dataset import (
    AggLevel,
    AggregatedPlan,
    build_aggregated_dataset,
    plan_aggregated,
)
from cellar.application.visualization.cross_protocol import join_protocol_datasets
from cellar.application.visualization.dataset import (
    Dataset,
    DatasetProtocol,
    build_wells_dataset,
)
from cellar.application.visualization.dataset_reader import (
    ReadoutDefInfo,
    RunInfo,
    VisualizationDatasetReader,
)
from cellar.domain.shared.errors import DomainError, NotFoundError, ValidationError

# Benchmarked on 384-well plates (raw + one normalized layer): 100k rows
# build and serialize in about 1.8 s, 200k in about 3.4 s. Cost follows readout values
# (rows x value columns); the column cap guards payload size, not latency.
MAX_DATASET_ROWS = 100_000
MAX_DATASET_COLUMNS = 400

DatasetLevel = Literal["wells", "runs", "batches", "compounds"]


@dataclass(frozen=True)
class ComparedProtocol:
    protocol_id: uuid.UUID
    run_ids: tuple[uuid.UUID, ...] | None = None


@dataclass(frozen=True)
class ProtocolSource:
    protocol_id: uuid.UUID
    run_ids: tuple[uuid.UUID, ...] | None = None
    # Compounds level only: further protocols joined onto this one's compounds.
    compare: tuple[ComparedProtocol, ...] = ()


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


def _too_many_columns(
    total: int, level: DatasetLevel, *, at_least: bool = False, compared: bool = False
) -> ValidationError:
    # Aggregated columns multiply with condition sets and layers, not with runs.
    if level == "wells":
        hint = "Choose fewer runs."
    elif compared:
        hint = (
            "Each compared protocol, condition set and normalization layer adds its own "
            "columns: compare fewer protocols or choose runs with fewer condition sets."
        )
    else:
        hint = (
            "Each condition set and normalization layer adds its own columns: "
            "choose runs with fewer condition sets."
        )
    has = "at least " if at_least else ""
    return ValidationError(
        f"This selection has {has}{total:,} columns; the limit is {MAX_DATASET_COLUMNS:,}. {hint}"
    )


def compare_error(protocol_ids: Sequence[uuid.UUID], level: str) -> ValidationError | None:
    """Why this source can't be loaded: protocols after the first are compared, which works
    at the Compounds level only and with each protocol once. Saving a view asks the same."""
    if len(protocol_ids) < 2:
        return None
    if level != "compounds":
        return ValidationError("Comparing protocols works at the Compounds level only.")
    if len(set(protocol_ids)) < len(protocol_ids):
        return ValidationError("Each protocol can be loaded once.")
    return None


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
        ws, src = input.workspace_id, input.source
        compare = src.compare if isinstance(src, ProtocolSource) else ()
        if isinstance(src, ProtocolSource):
            refused = compare_error(
                [src.protocol_id, *(c.protocol_id for c in compare)], input.level
            )
            if refused is not None:
                return Failure(refused)

        runs = await self._resolve_runs(ws, src)
        if isinstance(runs, NotFoundError):
            return Failure(runs)
        # A source reads one protocol: the protocol itself, or the run's.
        parts = [
            (src.protocol_id if isinstance(src, ProtocolSource) else runs[0].protocol_id, runs)
        ]
        for c in compare:
            compared = await self._resolve_runs(ws, ProtocolSource(c.protocol_id, c.run_ids))
            if isinstance(compared, NotFoundError):
                return Failure(compared)
            parts.append((c.protocol_id, compared))

        datasets = (
            await self._wells(ws, runs)
            if input.level == "wells"
            else await self._aggregated(ws, parts, input.level)
        )
        if isinstance(datasets, ValidationError):
            return Failure(datasets)
        pids = [pid for pid, _ in parts]
        names = await self._reader.protocol_names(ws, pids)
        signals = await self._reader.pos_control_signals(ws, pids)
        dataset = join_protocol_datasets(
            [
                (DatasetProtocol(pid, names[pid], signals.get(pid, "high")), part)
                for (pid, _), part in zip(parts, datasets, strict=True)
            ]
        )
        if len(dataset.row_ids) > MAX_DATASET_ROWS:
            return Failure(_too_many_rows(len(dataset.row_ids)))
        if len(dataset.columns) > MAX_DATASET_COLUMNS:
            return Failure(
                _too_many_columns(len(dataset.columns), input.level, compared=bool(compare))
            )
        return Success(dataset)

    async def _wells(self, ws: uuid.UUID, runs: list[RunInfo]) -> list[Dataset] | ValidationError:
        run_ids = [r.id for r in runs]
        total = sum((await self._reader.count_wells_rows(ws, run_ids)).values())
        if total > MAX_DATASET_ROWS:
            return _too_many_rows(total)  # refused before loading anything

        qc = await self._reader.run_qc_metrics(ws, run_ids)
        runs = [replace(r, qc_metrics=qc.get(r.id)) for r in runs]
        defs = await self._reader.readout_definitions(ws, sorted({r.protocol_id for r in runs}))
        rows = await self._reader.fetch_well_values(ws, run_ids)
        molecules = await self._reader.compound_info(
            ws, list({r.molecule_id for r in rows if r.molecule_id is not None})
        )
        # About 1 s of pure CPU at the row cap: keep it off the event loop.
        return [await asyncio.to_thread(build_wells_dataset, runs, defs, rows, molecules)]

    async def _aggregated(
        self, ws: uuid.UUID, parts: list[tuple[uuid.UUID, list[RunInfo]]], level: AggLevel
    ) -> list[Dataset] | ValidationError:
        """One dataset per (protocol, runs), to be joined on the first one's rows."""
        # Refused before curves, compounds and the dense columns are loaded, and before the
        # next protocol is read. Every protocol is built in full; the join keeps the first
        # one's rows and columns, every added value and p column, a tested column per added
        # protocol and one selectivity column per pair of p columns.
        planned: list[tuple[ActivityAggregates, list[ReadoutDefInfo], AggregatedPlan]] = []
        rows = columns = 0
        for protocol_id, runs in parts:
            planned.append(await self._plan(ws, protocol_id, runs, level))
            plan, first = planned[-1][2], planned[0][2]
            rows = max(rows, plan.rows)
            columns += (
                plan.columns if plan is first else plan.values + plan.p + 1 + first.p * plan.p
            )
            if rows > MAX_DATASET_ROWS:
                return _too_many_rows(rows)
            if columns > MAX_DATASET_COLUMNS:
                return _too_many_columns(columns, level, at_least=True, compared=len(parts) > 1)
        return [
            await self._build(ws, runs, defs, aggregates, level)
            for (_, runs), (aggregates, defs, _) in zip(parts, planned, strict=True)
        ]

    async def _plan(
        self, ws: uuid.UUID, protocol_id: uuid.UUID, runs: list[RunInfo], level: AggLevel
    ) -> tuple[ActivityAggregates, list[ReadoutDefInfo], AggregatedPlan]:
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
        defs = await self._reader.readout_definitions(ws, [protocol_id])
        return aggregates, defs, plan_aggregated(level, runs, defs, aggregates)

    async def _build(
        self,
        ws: uuid.UUID,
        runs: list[RunInfo],
        defs: list[ReadoutDefInfo],
        aggregates: ActivityAggregates,
        level: AggLevel,
    ) -> Dataset:
        run_ids = [r.id for r in runs]
        curves = await self._reader.fetch_curves(ws, run_ids) if level == "runs" else []
        records: list[NumericReadoutRow | DRAggRow | CurveRow] = [
            *aggregates.numeric_rows,
            *aggregates.dr_agg_rows,
            *curves,
        ]
        molecules = await self._reader.compound_info(ws, list({r.molecule_id for r in records}))
        batches = await self._reader.batch_numbers(
            ws, list({r.batch_id for r in records if r.batch_id is not None})
        )
        return await asyncio.to_thread(
            build_aggregated_dataset, level, runs, defs, aggregates, curves, molecules, batches
        )
