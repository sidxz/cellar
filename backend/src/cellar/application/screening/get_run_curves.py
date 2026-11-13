"""GetRunCurves query: a run's measured curves for one channel, with its holder and positions."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Failure, Result, Success

from cellar.application.auth import AuthContext, require_same_workspace, require_workspace_role
from cellar.application.screening.plate_map_reader import PlateMapReader, WellMapEntry
from cellar.application.shared.query import Query
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.screening_assay.curve_derivative import CurveDerivativeService, default_window
from cellar.domain.screening_assay.enums import HolderKind
from cellar.domain.screening_assay.holder import holder_label
from cellar.domain.screening_assay.measured_curve import CurveChannel, ReportedPoint
from cellar.domain.screening_assay.repository import MeasuredCurveRepository
from cellar.domain.shared.errors import DomainError, NotFoundError, ValidationError


@dataclass(frozen=True, kw_only=True)
class GetRunCurvesQuery(Query):
    workspace_id: uuid.UUID
    run_id: uuid.UUID
    channel: str | None = None
    view: str = "measured"  # "measured" | "derivative"
    window: float | None = None  # derivative smoothing window, in x units


@dataclass(frozen=True)
class CurveSeries:
    well_id: uuid.UUID
    x: tuple[float, ...]
    y: tuple[float, ...]
    reported: tuple[ReportedPoint, ...]


@dataclass(frozen=True)
class RunCurves:
    run_id: uuid.UUID
    dose_unit: str
    holder_kind: str
    holder_rows: int | None
    holder_columns: int | None
    holder_label: str
    positions: tuple[WellMapEntry, ...]  # the holder's used positions
    channels: tuple[CurveChannel, ...]  # ordered by channel order
    channel: CurveChannel | None  # the one whose curves are returned
    curves: tuple[CurveSeries, ...]
    view: str = "measured"
    window: float | None = None  # the window used; None for measured


class GetRunCurves:
    """Return the curves of one channel (the one asked for, else the first) of a run."""

    def __init__(
        self,
        uow: UnitOfWork,
        curve_repo: MeasuredCurveRepository,
        plate_map_reader: PlateMapReader,
        derivative: CurveDerivativeService,
    ) -> None:
        self._uow = uow
        self._curve_repo = curve_repo
        self._plate_map_reader = plate_map_reader
        self._derivative = derivative

    async def __call__(
        self, input: GetRunCurvesQuery, auth: AuthContext | None = None
    ) -> Result[RunCurves, DomainError]:
        require_workspace_role(auth, "viewer")
        require_same_workspace(auth, input.workspace_id)

        ws = input.workspace_id
        async with self._uow:
            plate_map = await self._plate_map_reader.get_plate_map(ws, input.run_id)
            if plate_map is None:
                return Failure(NotFoundError("Run", str(input.run_id)))

            channels = tuple(await self._curve_repo.list_channels(ws, input.run_id))
            channel = None
            if input.channel is not None:
                channel = next((c for c in channels if c.key == input.channel), None)
                if channel is None:
                    return Failure(ValidationError(f"Unknown channel '{input.channel}'"))
            elif channels:
                channel = channels[0]

            curves = (
                await self._curve_repo.find_by_run(ws, input.run_id, channel_key=channel.key)
                if channel is not None
                else []
            )

        curve_wells = {c.well_id for c in curves}
        plates = plate_map.plates
        holder = next(
            (p for p in plates if any(w.well_id in curve_wells for w in p.wells)),
            plates[0] if plates else None,
        )
        positions = tuple(holder.wells) if holder else ()
        order = {w.well_id: i for i, w in enumerate(positions)}
        kind = holder.holder_kind if holder else HolderKind.PLATE.value
        rows = holder.holder_rows if holder else None
        columns = holder.holder_columns if holder else None

        series = [
            CurveSeries(well_id=c.well_id, x=c.x, y=c.y, reported=c.reported)
            for c in sorted(curves, key=lambda c: order.get(c.well_id, len(order)))
        ]
        window: float | None = None
        if input.view == "derivative" and series:
            # One window for the whole response; calculated here, never stored.
            ranges = [(min(s.x), max(s.x)) for s in series]
            widest = max(hi - lo for lo, hi in ranges)
            if input.window is not None and not 0 < input.window <= widest:
                return Failure(
                    ValidationError(
                        f"The derivative window must be a number above 0 and at most {widest:g}, "
                        "the widest x range of the curves"
                    )
                )
            window = input.window or default_window(ranges)
            series = [d for d in (self._differentiate(s, window) for s in series) if d.x]
        elif input.view == "derivative":
            window = input.window

        return Success(
            RunCurves(
                run_id=input.run_id,
                dose_unit=plate_map.dose_unit,
                holder_kind=kind,
                holder_rows=rows,
                holder_columns=columns,
                holder_label=holder_label(HolderKind(kind), rows, columns),
                positions=positions,
                channels=channels,
                channel=channel,
                curves=tuple(series),
                view=input.view,
                window=window,
            )
        )

    def _differentiate(self, s: CurveSeries, window: float) -> CurveSeries:
        d = self._derivative.derivative(s.x, s.y, window=window)
        return CurveSeries(well_id=s.well_id, x=d.x, y=d.y, reported=s.reported)
