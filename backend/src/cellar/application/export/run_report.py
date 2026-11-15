"""A run's thermal shift results, gathered for export as the Traces tab shows them.

The results table (lib/melt-results.ts): one row per position with its Tm and ΔTm
per window, the window status the page shows, and the run's hit call
(lib/melt-hits.ts: a sample meeting every rule on a per-position Tm or ΔTm; a
missing value fails its rule). Then the melting steps with their review, and
every signal's traces, measured and as the derivative.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date, datetime

from returns.result import Success

from cellar.application.auth import AuthContext
from cellar.application.screening.get_melting_analysis import (
    GetMeltingAnalysis,
    GetMeltingAnalysisQuery,
    MeltingAnalysis,
    WindowAnalysis,
)
from cellar.application.screening.get_run_curves import GetRunCurves, GetRunCurvesQuery
from cellar.application.screening.plate_map_reader import WellMapEntry
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.screening_assay.melt_window import MeltMeasure, WindowFlag
from cellar.domain.screening_assay.melting_step import MeltingStep, MeltingStepStatus
from cellar.domain.screening_assay.repository import ProtocolRepository, RunRepository
from cellar.domain.shared.errors import NotFoundError
from cellar.domain.shared.hit_criterion import HitCriterion

# The page's status badges (melt-results-grid.tsx STATUS).
REFERENCE = "Reference"
SEVERAL_STEPS = "Several steps"
NO_STEP = "No step"
NO_REFERENCE = "No reference"
PROVISIONAL = "Provisional"
REVIEWED = "Reviewed"
DIFFERS = "step count differs from the reference"

_OPERATORS = {"gt": ">", "gte": "≥", "lt": "<", "lte": "≤"}


@dataclass(frozen=True)
class RunWindow:
    name: str
    channel_label: str
    low: float
    high: float
    reference_tm: float | None
    reference_count: int
    # The run's rule on this window's ΔTm, drawn on its shift plot (melt-hits.ts
    # bandFor): "outside" as a band, a one-sided rule as a line.
    band: tuple[float, float] | None = None
    line: float | None = None


@dataclass(frozen=True)
class RunCell:
    tm: float | None
    delta_tm: float | None
    status: str


@dataclass(frozen=True)
class RunRow:
    well_id: uuid.UUID
    position: str
    sample: str  # registration number, else label, else position (sampleTextOf)
    registration_number: str | None
    batch: str | None
    label: str | None
    concentration: float | None
    role: str  # sample, reference, control
    note: str | None
    cells: Mapping[str, RunCell]
    hit: bool | None  # None: not a sample, or the run has no rule on these values


@dataclass(frozen=True)
class RunStep:
    position: str
    sample: str
    signal: str
    value: float
    source: str
    status: str
    instrument_value: float | None
    reason: str | None
    changed_by: str | None
    changed_at: datetime | None


@dataclass(frozen=True)
class RunTrace:
    position: str
    sample: str
    role: str
    hit: bool | None
    x: tuple[float, ...]
    y: tuple[float, ...]


@dataclass(frozen=True)
class RunSignal:
    """One signal's traces in one view (measured, or the derivative at ``window``)."""

    key: str
    label: str
    view: str
    x_label: str
    y_label: str
    window: float | None
    traces: tuple[RunTrace, ...]


@dataclass(frozen=True)
class RunReport:
    protocol: str  # "PRT-00219 M. tuberculosis HsaA/B binding"
    run_date: date
    status: str
    operator: str | None
    holder: str  # the holder as the instrument reader names it
    notes: str | None
    dose_unit: str
    windows: tuple[RunWindow, ...]
    hit_rule: tuple[str, ...]  # one line per rule, as stated on the run
    rows: tuple[RunRow, ...]
    steps: tuple[RunStep, ...]
    signals: tuple[RunSignal, ...] = field(default=())

    @property
    def summary(self) -> str:
        return f"{self.protocol} · run of {self.run_date.isoformat()} · {self.holder}"

    @property
    def analysis_signal(self) -> str | None:
        """The signal the windows read their steps from (they share one)."""
        return self.windows[0].channel_label if self.windows else None


class BuildRunReport:
    """Gather a run's report from the same queries the Traces tab reads."""

    def __init__(
        self,
        uow: UnitOfWork,
        run_repo: RunRepository,
        protocol_repo: ProtocolRepository,
        get_analysis: GetMeltingAnalysis,
        get_curves: GetRunCurves,
    ) -> None:
        self._uow = uow
        self._run_repo = run_repo
        self._protocol_repo = protocol_repo
        self._get_analysis = get_analysis
        self._get_curves = get_curves

    async def __call__(
        self,
        *,
        workspace_id: uuid.UUID,
        run_id: uuid.UUID,
        people: Mapping[str, str],
        auth: AuthContext,
    ) -> RunReport:
        async with self._uow:
            run = await self._run_repo.find_by_id_in_workspace(workspace_id, run_id)
            if run is None:
                raise NotFoundError("Run", str(run_id))
            protocol = await self._protocol_repo.find_by_id_in_workspace(
                workspace_id, run.protocol_id
            )
            if protocol is None:
                raise NotFoundError("Protocol", str(run.protocol_id))

        analysis = _unwrap(
            await self._get_analysis(
                GetMeltingAnalysisQuery(workspace_id=workspace_id, run_id=run_id), auth=auth
            )
        )
        first = _unwrap(
            await self._get_curves(
                GetRunCurvesQuery(workspace_id=workspace_id, run_id=run_id), auth=auth
            )
        )
        positions = first.positions
        channels = {c.key: c for c in first.channels}

        melt = {rd.name: rd.melt_config for rd in protocol.readout_definitions if rd.melt_config}
        rules = list(run.hit_criteria or [])
        applicable = [
            (rule, mc.window, mc.measure)
            for rule in rules
            if (mc := melt.get(rule.readout_name)) is not None
            and mc.measure in (MeltMeasure.TM, MeltMeasure.DELTA_TM)
        ]
        units = {rd.name: rd.unit for rd in protocol.readout_definitions}
        rows = _rows(positions, analysis, applicable)
        names = {r.well_id: (r.position, r.sample) for r in rows}
        hits = {r.well_id: r.hit for r in rows}
        roles = {r.well_id: r.role for r in rows}

        signals: list[RunSignal] = []
        for channel in first.channels:
            for view in ("measured", "derivative"):
                got = _unwrap(
                    await self._get_curves(
                        GetRunCurvesQuery(
                            workspace_id=workspace_id,
                            run_id=run_id,
                            channel=channel.key,
                            view=view,
                        ),
                        auth=auth,
                    )
                )
                x_label = f"{channel.x_label or 'x'} ({channel.x_unit})"
                y_label = (
                    channel.label
                    if view == "measured"
                    else f"Derivative of {channel.label} (1/{channel.x_unit})"
                )
                signals.append(
                    RunSignal(
                        key=channel.key,
                        label=channel.label,
                        view=view,
                        x_label=x_label,
                        y_label=y_label,
                        window=got.window,
                        traces=tuple(
                            RunTrace(
                                position=names.get(c.well_id, ("", ""))[0],
                                sample=names.get(c.well_id, ("", ""))[1],
                                role=roles.get(c.well_id, "sample"),
                                hit=hits.get(c.well_id),
                                x=c.x,
                                y=c.y,
                            )
                            for c in got.curves
                        ),
                    )
                )

        return RunReport(
            protocol=" ".join(p for p in (protocol.code, protocol.name) if p),
            run_date=run.run_date,
            status=str(run.status.value if hasattr(run.status, "value") else run.status),
            operator=people.get(str(run.operator)) if run.operator else None,
            holder=first.holder_label,
            notes=run.notes,
            dose_unit=str(first.dose_unit),
            windows=tuple(
                RunWindow(
                    name=w.window,
                    channel_label=channels[w.channel_key].label
                    if w.channel_key in channels
                    else w.channel_key,
                    low=w.low,
                    high=w.high,
                    reference_tm=w.result.reference_tm,
                    reference_count=w.result.reference_count,
                    **_band(w.window, applicable),
                )
                for w in analysis.windows
            ),
            hit_rule=tuple(rule_text(r, units.get(r.readout_name)) for r in rules),
            rows=tuple(rows),
            steps=tuple(_steps(analysis.steps, names, channels, people)),
            signals=tuple(signals),
        )


def _band(window: str, applicable: list[tuple[HitCriterion, str, MeltMeasure]]) -> dict:
    rule = next((r for r, w, m in applicable if w == window and m == MeltMeasure.DELTA_TM), None)
    if rule is None:
        return {}
    v = rule.value
    if rule.operator == "not_between" and isinstance(v, list) and len(v) == 2:
        return {"band": (float(v[0]), float(v[1]))}
    return {"line": float(v)} if isinstance(v, int | float) else {}


def rule_text(rule: HitCriterion, unit: str | None) -> str:
    """The rule as stated: "ΔTm (Main) outside -2 to 2 °C" (a true minus), "Tm (Low) > 40 °C"."""
    u = f" {unit}" if unit else ""
    value = rule.value
    if rule.operator in ("not_between", "between") and isinstance(value, list) and len(value) == 2:
        word = "outside" if rule.operator == "not_between" else "between"
        return f"{rule.readout_name} {word} {_num(value[0])} to {_num(value[1])}{u}"
    if isinstance(value, list):
        return f"{rule.readout_name} {rule.operator} {', '.join(map(str, value))}"
    return f"{rule.readout_name} {_OPERATORS.get(rule.operator, rule.operator)} {_num(value)}{u}"


def _num(v: object) -> str:
    """A bound as the page writes it, with a true minus sign."""
    return f"\u2212{abs(v):g}" if isinstance(v, int | float) and v < 0 else f"{v:g}"  # type: ignore[str-format]


def _rows(
    positions: tuple[WellMapEntry, ...],
    analysis: MeltingAnalysis,
    applicable: list[tuple[HitCriterion, str, MeltMeasure]],
) -> list[RunRow]:
    differs = {c.channel_key: c.check.differs for c in analysis.step_checks}
    by_window = {w.window: w for w in analysis.windows}
    rows: list[RunRow] = []
    for p in positions:
        cells: dict[str, RunCell] = {}
        for w in analysis.windows:
            r = next((x for x in w.result.positions if x.well_id == p.well_id), None)
            if r is None:
                continue
            status = _status(p.well_type, r.flags, _counting(w, p.well_id, analysis.steps))
            if p.well_id in differs.get(w.channel_key, ()):
                status = f"{status} · {DIFFERS}"
            cells[w.window] = RunCell(tm=r.tm, delta_tm=r.delta_tm, status=status)
        rows.append(
            RunRow(
                well_id=p.well_id,
                position=p.position_label or p.position,
                sample=p.registration_number or p.label or p.position_label or p.position,
                registration_number=p.registration_number,
                batch=_batch_suffix(p),
                label=p.label,
                concentration=p.dose,
                role=p.well_type,
                note=p.note,
                cells=cells,
                hit=_hit(p, by_window, applicable),
            )
        )
    return rows


def _hit(
    p: WellMapEntry,
    by_window: Mapping[str, WindowAnalysis],
    applicable: list[tuple[HitCriterion, str, MeltMeasure]],
) -> bool | None:
    if p.well_type != "sample" or not applicable:
        return None
    for rule, window, measure in applicable:
        w = by_window.get(window)
        r = next((x for x in w.result.positions if x.well_id == p.well_id), None) if w else None
        value = None if r is None else (r.tm if measure == MeltMeasure.TM else r.delta_tm)
        if value is None or not rule.is_met(value):
            return False
    return True


def _counting(w: WindowAnalysis, well_id: uuid.UUID, steps: tuple[MeltingStep, ...]):
    """The step giving a position its Tm in a window: not rejected, on the
    window's signal, inside it."""
    return next(
        (
            s
            for s in steps
            if s.well_id == well_id
            and s.channel_key == w.channel_key
            and s.status != MeltingStepStatus.REJECTED
            and w.low <= s.value <= w.high
        ),
        None,
    )


def _status(well_type: str, flags, counting: MeltingStep | None) -> str:
    if well_type == "reference":
        return REFERENCE
    if WindowFlag.SEVERAL_STEPS in flags:
        return SEVERAL_STEPS
    if WindowFlag.NO_STEP in flags:
        return NO_STEP
    if WindowFlag.NO_REFERENCE in flags:
        return NO_REFERENCE
    return (
        PROVISIONAL if counting and counting.status == MeltingStepStatus.UNREVIEWED else REVIEWED
    )


def _batch_suffix(p: WellMapEntry) -> str | None:
    """The batch number without its registration-number prefix (`001`)."""
    if not p.batch_number:
        return None
    prefix = f"{p.registration_number}-"
    if p.registration_number and p.batch_number.startswith(prefix):
        return p.batch_number[len(prefix) :]
    return p.batch_number


def _steps(
    steps: tuple[MeltingStep, ...],
    names: Mapping[uuid.UUID, tuple[str, str]],
    channels: Mapping,
    people: Mapping[str, str],
) -> list[RunStep]:
    return [
        RunStep(
            position=names.get(s.well_id, ("", ""))[0],
            sample=names.get(s.well_id, ("", ""))[1],
            signal=channels[s.channel_key].label if s.channel_key in channels else s.channel_key,
            value=s.value,
            source=s.source.value.capitalize(),
            status=s.status.value.capitalize(),
            instrument_value=s.instrument_value,
            reason=s.reason,
            changed_by=people.get(str(s.changed_by))
            or (str(s.changed_by) if s.changed_by else None),
            changed_at=s.changed_at,
        )
        for s in steps
    ]


def _unwrap(result):
    if not isinstance(result, Success):
        failure = result.failure()
        raise failure if isinstance(failure, Exception) else RuntimeError(str(failure))
    return result.unwrap()
