"""GetMeltingAnalysis query: a run's melting steps, window results and step-count checks."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Failure, Result, Success

from cellar.application.auth import AuthContext, require_same_workspace, require_workspace_role
from cellar.application.screening.manage_melting_steps import NOT_EDITABLE
from cellar.application.shared.query import Query
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.screening_assay.melt_series import SeriesValue, series_points, series_values
from cellar.domain.screening_assay.melt_window import (
    MeltMeasure,
    StepCountCheck,
    WindowResult,
    check_step_counts,
    evaluate_window,
    window_positions,
)
from cellar.domain.screening_assay.melting_step import MeltingStep
from cellar.domain.screening_assay.protocol import ReadoutDefinition
from cellar.domain.screening_assay.repository import (
    MeasuredCurveRepository,
    MeltingStepRepository,
    ProtocolRepository,
    RunRepository,
)
from cellar.domain.shared.errors import DomainError, NotFoundError

LOCKED = "This run is locked"


@dataclass(frozen=True, kw_only=True)
class GetMeltingAnalysisQuery(Query):
    workspace_id: uuid.UUID
    run_id: uuid.UUID


@dataclass(frozen=True)
class WindowSeries:
    """A series readout of a window and its value per batch, as the engine computes it."""

    readout_id: uuid.UUID
    readout_name: str
    measure: MeltMeasure
    threshold: float | None
    concentration: float | None
    values: tuple[SeriesValue, ...]


@dataclass(frozen=True)
class WindowAnalysis:
    window: str
    channel_key: str
    low: float
    high: float
    tm_readout_id: uuid.UUID | None
    delta_tm_readout_id: uuid.UUID | None
    result: WindowResult
    series: tuple[WindowSeries, ...] = ()


@dataclass(frozen=True)
class ChannelStepCheck:
    channel_key: str
    check: StepCountCheck


@dataclass(frozen=True)
class MeltingAnalysis:
    run_id: uuid.UUID
    edit_refusal: str | None  # None when steps can be edited
    steps: tuple[MeltingStep, ...]  # ordered by well, channel, value
    windows: tuple[WindowAnalysis, ...]  # ordered by low
    step_checks: tuple[ChannelStepCheck, ...]  # one per channel that has steps


class GetMeltingAnalysis:
    def __init__(
        self,
        uow: UnitOfWork,
        run_repo: RunRepository,
        protocol_repo: ProtocolRepository,
        step_repo: MeltingStepRepository,
        curve_repo: MeasuredCurveRepository,
    ) -> None:
        self._uow = uow
        self._run_repo = run_repo
        self._protocol_repo = protocol_repo
        self._step_repo = step_repo
        self._curve_repo = curve_repo

    async def __call__(
        self, input: GetMeltingAnalysisQuery, auth: AuthContext | None = None
    ) -> Result[MeltingAnalysis, DomainError]:
        require_workspace_role(auth, "viewer")
        require_same_workspace(auth, input.workspace_id)
        ws = input.workspace_id

        async with self._uow:
            run = await self._run_repo.find_by_id_in_workspace(ws, input.run_id)
            if run is None:
                return Failure(NotFoundError("Run", str(input.run_id)))
            protocol = await self._protocol_repo.find_by_id_in_workspace(ws, run.protocol_id)
            if protocol is None:
                return Failure(NotFoundError("Protocol", str(run.protocol_id)))
            found = await self._step_repo.find_by_run(ws, run.id)
            traced = await self._curve_repo.list_traced(ws, run.id)

        order = {w.id: i for i, w in enumerate(run.wells)}
        steps = tuple(
            sorted(found, key=lambda s: (order.get(s.well_id, len(order)), s.channel_key, s.value))
        )
        wells = [(w.id, w.well_type) for w in run.wells]
        counted = [(s.well_id, s.channel_key, s.value, s.counts) for s in steps]

        batch_and_dose = {w.id: (w.batch_id, w.dose) for w in run.wells}

        # Readouts of one window share its channel and limits (Protocol enforces it).
        per_position: dict[str, dict[MeltMeasure, uuid.UUID]] = {}
        series_defs: dict[str, list[ReadoutDefinition]] = {}
        shape: dict[str, tuple[str, float, float]] = {}
        for rd in protocol.readout_definitions:
            if (mc := rd.melt_config) is None:
                continue
            shape[mc.window] = (mc.channel_key, mc.low, mc.high)
            if mc.measure.is_series:
                series_defs.setdefault(mc.window, []).append(rd)
            else:
                per_position.setdefault(mc.window, {})[mc.measure] = rd.id

        def analyse(name: str, channel: str, low: float, high: float) -> WindowAnalysis:
            result = evaluate_window(low, high, window_positions(wells, counted, channel, traced))
            points = series_points(result, batch_and_dose)
            ids = per_position.get(name, {})
            return WindowAnalysis(
                window=name,
                channel_key=channel,
                low=low,
                high=high,
                tm_readout_id=ids.get(MeltMeasure.TM),
                delta_tm_readout_id=ids.get(MeltMeasure.DELTA_TM),
                result=result,
                series=tuple(
                    WindowSeries(
                        readout_id=rd.id,
                        readout_name=rd.name,
                        measure=rd.melt_config.measure,  # type: ignore[union-attr]
                        threshold=rd.melt_config.threshold,  # type: ignore[union-attr]
                        concentration=rd.melt_config.concentration,  # type: ignore[union-attr]
                        values=tuple(series_values(rd.melt_config, points)),  # type: ignore[arg-type]
                    )
                    for rd in series_defs.get(name, [])
                ),
            )

        windows = tuple(
            analyse(name, channel, low, high)
            for name, (channel, low, high) in sorted(shape.items(), key=lambda kv: kv[1][1])
        )
        step_checks = tuple(
            ChannelStepCheck(ch, check_step_counts(window_positions(wells, counted, ch, traced)))
            for ch in sorted({s.channel_key for s in steps})
        )

        refusal = None if run.calculated_positions_editable else NOT_EDITABLE
        if run.is_locked:
            refusal = LOCKED
        return Success(MeltingAnalysis(run.id, refusal, steps, windows, step_checks))
