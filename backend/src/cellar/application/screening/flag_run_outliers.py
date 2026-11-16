"""FlagRunOutliers: flag wells of a run as outliers, or remove their flag.

Every raw readout row of the named wells takes the flag. An outlier leaves plate QC and
the normalization anchors and keeps its own normalized value. Refused on a locked,
approved or rejected run; a completed run needs a reason. Audited per position.

One transaction: the flags, the recalculation (normalization, plate QC, formulas) and
the refit of the curves the change touches — with their chemists' exclusions and fit
settings kept — commit together, or nothing does. Saving the run bumps its version, so
an approval or lock saved meanwhile makes this (or that) a concurrency conflict.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Failure, Result, Success

from cellar.application.auth import AuthContext, require_editor, require_same_workspace
from cellar.application.screening.readout_calculation_engine import ReadoutCalculationEngine
from cellar.application.screening.refit_curves_keeping_edits import RefitCurvesKeepingEdits
from cellar.application.shared.command import Command
from cellar.application.shared.event_dispatcher import EventDispatcherProtocol
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.screening_assay.repository import (
    ProtocolRepository,
    ReadoutDataRepository,
    RunRepository,
)
from cellar.domain.shared.errors import ConflictError, DomainError, NotFoundError, ValidationError


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
    # Curves the change removed, or exclusions it could not keep.
    compute_warning: str | None = None


class FlagRunOutliers:
    def __init__(
        self,
        uow: UnitOfWork,
        run_repo: RunRepository,
        readout_repo: ReadoutDataRepository,
        protocol_repo: ProtocolRepository,
        calculation_engine: ReadoutCalculationEngine,
        curves: RefitCurvesKeepingEdits,
        dispatcher: EventDispatcherProtocol,
    ) -> None:
        # The engine and ``curves`` work in this use case's unit of work.
        self._uow = uow
        self._run_repo = run_repo
        self._readout_repo = readout_repo
        self._protocol_repo = protocol_repo
        self._calculation_engine = calculation_engine
        self._curves = curves
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
                run.check_outlier_flags(well_ids, reason=input.reason)
            except (ValidationError, ConflictError) as exc:
                return Failure(exc)
            protocol = await self._protocol_repo.find_by_id_in_workspace(ws, run.protocol_id)
            if protocol is None:
                return Failure(NotFoundError("Protocol", str(run.protocol_id)))

            before = await self._readout_repo.find_by_run(ws, run.id)
            changed = await self._readout_repo.set_outlier(
                ws, run.id, well_ids, outlier=input.outlier
            )
            if not changed:
                return Success(OutlierFlagResult(0, False))
            run.flag_outliers(changed, outlier=input.outlier, reason=input.reason)
            await self._run_repo.save(run)

            computed = await self._calculation_engine.compute_for_run(
                run.id, workspace_id=ws, refit_curves=False
            )
            if isinstance(computed, Failure):
                # Leaving the block without a commit rolls the flags back.
                return Failure(
                    ValidationError(
                        "Not saved: with these flags the run cannot be recalculated — "
                        f"{computed.failure().message}"
                    )
                )
            after = await self._readout_repo.find_by_run(ws, run.id)
            refit = await self._curves.refit(
                run=run, protocol=protocol, before=before, after=after
            )
            events = await self._uow.commit()

        await self._dispatcher.dispatch_all(events)
        return Success(OutlierFlagResult(len(changed), True, refit.warning()))
