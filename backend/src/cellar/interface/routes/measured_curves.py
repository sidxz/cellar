"""Measured curves of a run: the curves an instrument recorded at each position."""

from __future__ import annotations

import uuid
from typing import Literal

from fastapi import APIRouter, Query
from pydantic import BaseModel

from cellar.application.screening.get_run_curves import GetRunCurvesQuery, RunCurves
from cellar.interface.dependencies import AuthDep, GetRunCurvesDep
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
            channels=[
                CurveChannelModel(
                    key=c.key, label=c.label, x_unit=c.x_unit, y_unit=c.y_unit, x_label=c.x_label
                )
                for c in out.channels
            ],
            channel=out.channel.key if out.channel else None,
            view=out.view,
            window=out.window,
            curves=[
                CurveSeriesModel(
                    well_id=c.well_id,
                    x=list(c.x),
                    y=list(c.y),
                    reported=[
                        ReportedPointModel(
                            kind=r.kind,
                            ordinal=r.ordinal,
                            label=r.label,
                            value=r.value,
                            unit=r.unit,
                        )
                        for r in c.reported
                    ],
                )
                for c in out.curves
            ],
        )


@router.get("/runs/{run_id}/curves", response_model=RunCurvesResponse)
async def get_run_curves(
    run_id: uuid.UUID,
    auth: AuthDep,
    uc: GetRunCurvesDep,
    channel: str | None = None,
    view: Literal["measured", "derivative"] = "measured",
    window: float | None = Query(None, gt=0),
) -> RunCurvesResponse:
    """The run's holder, positions and channels, with the curves of one channel
    (the one asked for, else the first). ``view=derivative`` returns the smoothed first
    derivative instead, calculated on request (``window`` in x units, default 5% of the
    widest x range) and never stored."""
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
