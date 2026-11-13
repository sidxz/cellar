"""GetMeasuredCurvesBatch query: the curves of one channel for a list of positions."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.pipeline import is_successful
from returns.result import Failure, Result, Success

from cellar.application.auth import AuthContext, require_same_workspace, require_workspace_role
from cellar.application.screening.get_run_curves import CurveSeries, apply_view
from cellar.application.shared.query import Query
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.screening_assay.curve_derivative import CurveDerivativeService
from cellar.domain.screening_assay.repository import MeasuredCurveRepository
from cellar.domain.shared.errors import DomainError, ValidationError

MAX_CURVES_PER_REQUEST = 100


@dataclass(frozen=True, kw_only=True)
class GetMeasuredCurvesBatchQuery(Query):
    workspace_id: uuid.UUID
    well_ids: tuple[uuid.UUID, ...]
    channel: str
    view: str = "measured"  # "measured" | "derivative"
    window: float | None = None  # derivative smoothing window, in x units


@dataclass(frozen=True)
class MeasuredCurvesBatch:
    channel: str
    view: str
    window: float | None  # the window used; None for measured
    curves: tuple[CurveSeries, ...]  # in the order the positions were asked for


class GetMeasuredCurvesBatch:
    """Return the curves of one channel for the positions asked for, in that order.

    A position with no curve on the channel, or in another workspace, is absent.
    """

    def __init__(
        self,
        uow: UnitOfWork,
        curve_repo: MeasuredCurveRepository,
        derivative: CurveDerivativeService,
    ) -> None:
        self._uow = uow
        self._curve_repo = curve_repo
        self._derivative = derivative

    async def __call__(
        self, input: GetMeasuredCurvesBatchQuery, auth: AuthContext | None = None
    ) -> Result[MeasuredCurvesBatch, DomainError]:
        require_workspace_role(auth, "viewer")
        require_same_workspace(auth, input.workspace_id)

        if len(input.well_ids) > MAX_CURVES_PER_REQUEST:
            return Failure(
                ValidationError(f"At most {MAX_CURVES_PER_REQUEST} positions per request")
            )
        well_ids = tuple(dict.fromkeys(input.well_ids))
        curves = []
        if well_ids:
            async with self._uow:
                curves = await self._curve_repo.find_by_wells(
                    input.workspace_id, well_ids, channel_key=input.channel
                )

        by_well = {c.well_id: c for c in curves}
        series = [
            CurveSeries(well_id=c.well_id, x=c.x, y=c.y, reported=c.reported)
            for c in (by_well[w] for w in well_ids if w in by_well)
        ]
        viewed = apply_view(
            series, view=input.view, window=input.window, derivative=self._derivative
        )
        if not is_successful(viewed):
            return Failure(viewed.failure())
        shown, window = viewed.unwrap()
        return Success(
            MeasuredCurvesBatch(
                channel=input.channel, view=input.view, window=window, curves=tuple(shown)
            )
        )
