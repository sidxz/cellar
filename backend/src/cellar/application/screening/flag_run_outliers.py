"""FlagRunOutliers: flag wells of a run as outliers, or remove their flag.

Every raw readout row of the named wells takes the flag. An outlier leaves plate QC and
the normalization anchors and keeps its own normalized value. Refused on a locked or
approved run. Audited per position; the calculation engine then runs for the run.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

import structlog
from returns.result import Failure, Result, Success

from cellar.application.auth import AuthContext, require_editor, require_same_workspace
from cellar.application.screening.readout_calculation_engine import ReadoutCalculationEngine
from cellar.application.shared.command import Command
from cellar.application.shared.event_dispatcher import EventDispatcherProtocol
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.screening_assay.repository import ReadoutDataRepository, RunRepository
from cellar.domain.shared.errors import ConflictError, DomainError, NotFoundError, ValidationError

_log = structlog.get_logger(__name__)


@dataclass(frozen=True, kw_only=True)
class FlagRunOutliersCommand(Command):
    workspace_id: uuid.UUID
    run_id: uuid.UUID
    well_ids: tuple[uuid.UUID, ...]
    outlier: bool
    reason: str | None = None


@dataclass(frozen=True)
class OutlierFlagResult:
    wells_changed: int
    recalculated: bool
    compute_warning: str | None = None


class FlagRunOutliers:
    def __init__(
        self,
        uow: UnitOfWork,
        run_repo: RunRepository,
        readout_repo: ReadoutDataRepository,
        calculation_engine: ReadoutCalculationEngine,
        dispatcher: EventDispatcherProtocol,
    ) -> None:
        self._uow = uow
        self._run_repo = run_repo
        self._readout_repo = readout_repo
        self._calculation_engine = calculation_engine
        self._dispatcher = dispatcher

    async def __call__(
        self, input: FlagRunOutliersCommand, auth: AuthContext | None = None
    ) -> Result[OutlierFlagResult, DomainError]:
        require_editor(auth)
        require_same_workspace(auth, input.workspace_id)

        ws = input.workspace_id
        well_ids = list(dict.fromkeys(input.well_ids))
        async with self._uow:
            run = await self._run_repo.find_by_id_in_workspace(ws, input.run_id)
            if run is None:
                return Failure(NotFoundError("Run", str(input.run_id)))
            try:
                run.check_outlier_flags(well_ids)
            except (ValidationError, ConflictError) as exc:
                return Failure(exc)

            changed = await self._readout_repo.set_outlier(
                ws, run.id, well_ids, outlier=input.outlier
            )
            if not changed:
                return Success(OutlierFlagResult(0, False))
            run.flag_outliers(changed, outlier=input.outlier, reason=input.reason)
            events = await self._uow.commit()

        await self._dispatcher.dispatch_all(events)

        computed = await self._calculation_engine.compute_for_run(run.id, workspace_id=ws)
        if isinstance(computed, Failure):
            message = computed.failure().message
            _log.warning(
                "run_outliers.compute_failed",
                run_id=str(run.id),
                workspace_id=str(ws),
                reason=message,
            )
            return Success(
                OutlierFlagResult(
                    len(changed),
                    False,
                    f"The flags were saved, but the run could not be recalculated: {message}",
                )
            )
        return Success(OutlierFlagResult(len(changed), True))
