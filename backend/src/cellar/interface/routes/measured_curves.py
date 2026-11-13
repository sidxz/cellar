"""Measured curves: the curves an instrument recorded at each position, for one run
or across the runs of a protocol."""

from __future__ import annotations

import uuid
from datetime import date
from typing import Literal

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from cellar.application.screening.curve_position_reader import CurvePositions, CurveRun
from cellar.application.screening.find_curve_positions import FindCurvePositionsQuery
from cellar.application.screening.get_measured_curves_batch import (
    MAX_CURVES_PER_REQUEST,
    GetMeasuredCurvesBatchQuery,
    MeasuredCurvesBatch,
)
from cellar.application.screening.get_run_curves import CurveSeries, GetRunCurvesQuery, RunCurves
from cellar.domain.screening_assay.measured_curve import CurveChannel
from cellar.interface.dependencies import (
    AuthDep,
    FindCurvePositionsDep,
    GetMeasuredCurvesBatchDep,
    GetRunCurvesDep,
)
from cellar.interface.error_handlers import result_to_response
from cellar.interface.routes.plate_setup import PlateMapWellModel
from cellar.interface.routes.run_import import CurveChannelModel, HolderModel

router = APIRouter(prefix="/api/v1", tags=["measured-curves"])


class ReportedPointModel(BaseModel):
    kind: str
    ordinal: int
    label: str
    value: float
    unit: str


class CurveSeriesModel(BaseModel):
    well_id: uuid.UUID
    x: list[float]
    y: list[float]
    reported: list[ReportedPointModel]

    @classmethod
    def from_series(cls, c: CurveSeries) -> CurveSeriesModel:
        return cls(
            well_id=c.well_id,
            x=list(c.x),
            y=list(c.y),
            reported=[
                ReportedPointModel(
                    kind=r.kind, ordinal=r.ordinal, label=r.label, value=r.value, unit=r.unit
                )
                for r in c.reported
            ],
        )


def _channel(c: CurveChannel) -> CurveChannelModel:
    return CurveChannelModel(
        key=c.key, label=c.label, x_unit=c.x_unit, y_unit=c.y_unit, x_label=c.x_label
    )


class RunCurvesResponse(BaseModel):
    run_id: uuid.UUID
    dose_unit: str
    holder: HolderModel
    positions: list[PlateMapWellModel]
    channels: list[CurveChannelModel]
    # Key of the channel whose curves are returned; null when the run has no curves.
    channel: str | None
    curves: list[CurveSeriesModel]
    # "measured" or "derivative"; for the derivative, the one smoothing window used (x units).
    view: str
    window: float | None

    @classmethod
    def from_result(cls, out: RunCurves) -> RunCurvesResponse:
        return cls(
            run_id=out.run_id,
            dose_unit=out.dose_unit,
            holder=HolderModel(
                kind=out.holder_kind,
                rows=out.holder_rows,
                columns=out.holder_columns,
                label=out.holder_label,
            ),
            positions=[PlateMapWellModel.from_entry(w) for w in out.positions],
            channels=[_channel(c) for c in out.channels],
            channel=out.channel.key if out.channel else None,
            view=out.view,
            window=out.window,
            curves=[CurveSeriesModel.from_series(c) for c in out.curves],
        )


class CurveRunModel(BaseModel):
    """A run with curves. Runs have no name: date, operator, status and notes tell them apart."""

    run_id: uuid.UUID
    run_date: date
    operator: uuid.UUID
    status: str
    notes: str | None
    holder: HolderModel
    channels: list[CurveChannelModel]
    # Positions with at least one curve.
    position_count: int

    @classmethod
    def from_run(cls, r: CurveRun) -> CurveRunModel:
        return cls(
            run_id=r.run_id,
            run_date=r.run_date,
            operator=r.operator,
            status=r.status,
            notes=r.notes,
            holder=HolderModel(
                kind=r.holder_kind,
                rows=r.holder_rows,
                columns=r.holder_columns,
                label=r.holder_label,
            ),
            channels=[_channel(c) for c in r.channels],
            position_count=r.position_count,
        )


class CurvePositionModel(PlateMapWellModel):
    run_id: uuid.UUID


class CurvePositionsResponse(BaseModel):
    protocol_id: uuid.UUID
    dose_unit: str
    # Every run of the protocol with curves, newest first, whatever the filters.
    runs: list[CurveRunModel]
    # Positions with curves matching the filters (none without a filter), in run order.
    positions: list[CurvePositionModel]

    @classmethod
    def from_result(cls, out: CurvePositions) -> CurvePositionsResponse:
        return cls(
            protocol_id=out.protocol_id,
            dose_unit=out.dose_unit,
            runs=[CurveRunModel.from_run(r) for r in out.runs],
            positions=[
                CurvePositionModel(
                    run_id=p.run_id, **PlateMapWellModel.from_entry(p.well).model_dump()
                )
                for p in out.positions
            ],
        )


class MeasuredCurvesBatchRequest(BaseModel):
    well_ids: list[uuid.UUID] = Field(max_length=MAX_CURVES_PER_REQUEST)
    channel: str
    view: Literal["measured", "derivative"] = "measured"
    window: float | None = Field(None, gt=0, allow_inf_nan=False)


class MeasuredCurvesBatchResponse(BaseModel):
    channel: str
    # "measured" or "derivative"; for the derivative, the one smoothing window used (x units).
    view: str
    window: float | None
    # In the order the positions were asked for; a position without a curve is absent.
    curves: list[CurveSeriesModel]

    @classmethod
    def from_result(cls, out: MeasuredCurvesBatch) -> MeasuredCurvesBatchResponse:
        return cls(
            channel=out.channel,
            view=out.view,
            window=out.window,
            curves=[CurveSeriesModel.from_series(c) for c in out.curves],
        )


@router.get("/runs/{run_id}/curves", response_model=RunCurvesResponse)
async def get_run_curves(
    run_id: uuid.UUID,
    auth: AuthDep,
    uc: GetRunCurvesDep,
    channel: str | None = None,
    view: Literal["measured", "derivative"] = "measured",
    window: float | None = Query(None, gt=0, allow_inf_nan=False),
) -> RunCurvesResponse:
    """The run's holder, positions and channels, with the curves of one channel
    (the one asked for, else the first). ``view=derivative`` returns the smoothed first
    derivative instead, calculated on request (``window`` in x units, default 5% of the
    widest x range; a wider window is clamped to that range) and never stored."""
    result = await uc(
        GetRunCurvesQuery(
            workspace_id=auth.workspace_id,
            run_id=run_id,
            channel=channel,
            view=view,
            window=window,
        ),
        auth=auth,
    )
    return RunCurvesResponse.from_result(result_to_response(result))


@router.get("/protocols/{protocol_id}/curve-positions", response_model=CurvePositionsResponse)
async def find_curve_positions(
    protocol_id: uuid.UUID,
    auth: AuthDep,
    uc: FindCurvePositionsDep,
    run_ids: list[uuid.UUID] = Query(default=[]),
    molecule_ids: list[uuid.UUID] = Query(default=[]),
) -> CurvePositionsResponse:
    """The protocol's runs with curves, and the positions with curves of the runs asked for
    (at most 8), of the compounds asked for (at most 50), or both; each contributing run's
    reference positions are added. Without a filter, ``positions`` is empty. No curve is
    returned: fetch them with ``POST /measured-curves:batch``."""
    result = await uc(
        FindCurvePositionsQuery(
            workspace_id=auth.workspace_id,
            protocol_id=protocol_id,
            run_ids=tuple(run_ids),
            molecule_ids=tuple(molecule_ids),
        ),
        auth=auth,
    )
    return CurvePositionsResponse.from_result(result_to_response(result))


@router.post("/measured-curves:batch", response_model=MeasuredCurvesBatchResponse)
async def get_measured_curves_batch(
    body: MeasuredCurvesBatchRequest,
    auth: AuthDep,
    uc: GetMeasuredCurvesBatchDep,
) -> MeasuredCurvesBatchResponse:
    """The curves of one channel for up to 100 positions, in the order asked for. A position
    without a curve on the channel, or not in the workspace, is absent. ``view=derivative``
    states the one window used (default 5% of the widest x range of these curves); send it
    back with later requests so every curve of a selection uses the same window."""
    result = await uc(
        GetMeasuredCurvesBatchQuery(
            workspace_id=auth.workspace_id,
            well_ids=tuple(body.well_ids),
            channel=body.channel,
            view=body.view,
            window=body.window,
        ),
        auth=auth,
    )
    return MeasuredCurvesBatchResponse.from_result(result_to_response(result))
