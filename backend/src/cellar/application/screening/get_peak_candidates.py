"""GetPeakCandidates query: the candidate peaks of one position of a run, on each signal."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.pipeline import is_successful
from returns.result import Failure, Result, Success

from cellar.application.auth import AuthContext, require_same_workspace, require_workspace_role
from cellar.application.screening.get_run_curves import smoothing_window
from cellar.application.shared.query import Query
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.screening_assay.measured_curve import MeasuredCurve
from cellar.domain.screening_assay.peak_detection import PeakCandidate, PeakDetectionService
from cellar.domain.screening_assay.repository import MeasuredCurveRepository, RunRepository
from cellar.domain.shared.errors import DomainError, NotFoundError


@dataclass(frozen=True, kw_only=True)
class GetPeakCandidatesQuery(Query):
    workspace_id: uuid.UUID
    run_id: uuid.UUID
    well_id: uuid.UUID
    smoothing_window: float | None = None  # in x units; None for the Traces view's default


@dataclass(frozen=True)
class SignalPeakCandidates:
    channel_key: str
    smoothing_window: float  # the one used
    candidates: tuple[PeakCandidate, ...]  # strongest first


class GetPeakCandidates:
    """One entry per signal the position has a trace on, in the run's signal order.

    Calculated on request, never stored. The smoothing of a signal is the one its derivative
    is viewed with: chosen over all the run's traces on that signal, not the position's own.
    """

    def __init__(
        self,
        uow: UnitOfWork,
        run_repo: RunRepository,
        curve_repo: MeasuredCurveRepository,
        detection: PeakDetectionService,
    ) -> None:
        self._uow = uow
        self._run_repo = run_repo
        self._curve_repo = curve_repo
        self._detection = detection

    async def __call__(
        self, input: GetPeakCandidatesQuery, auth: AuthContext | None = None
    ) -> Result[tuple[SignalPeakCandidates, ...], DomainError]:
        require_workspace_role(auth, "viewer")
        require_same_workspace(auth, input.workspace_id)
        ws = input.workspace_id

        async with self._uow:
            run = await self._run_repo.find_by_id_in_workspace(ws, input.run_id)
            if run is None:
                return Failure(NotFoundError("Run", str(input.run_id)))
            if all(w.id != input.well_id for w in run.wells):
                return Failure(NotFoundError("Position", str(input.well_id)))
            # ponytail: every trace of the run is read for the x ranges the smoothing is
            # chosen over. A reader of the ranges alone if this is slow on large plates.
            curves = await self._curve_repo.find_by_run(ws, run.id)

        by_signal: dict[str, list[MeasuredCurve]] = {}
        for curve in sorted(curves, key=lambda c: c.channel_order):
            by_signal.setdefault(curve.channel_key, []).append(curve)

        signals = []
        for key, traces in by_signal.items():
            own = next((c for c in traces if c.well_id == input.well_id), None)
            if own is None:
                continue
            chosen = smoothing_window([c.x for c in traces], input.smoothing_window)
            if not is_successful(chosen):
                return Failure(chosen.failure())
            used = chosen.unwrap()
            found = self._detection.candidates(own.x, own.y, window=used)
            signals.append(SignalPeakCandidates(key, used, found))
        return Success(tuple(signals))
