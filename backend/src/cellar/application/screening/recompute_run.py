"""RecomputeRun: re-run the calculation pipeline on a run's existing raw data.

An edit of the run's data like any other: editors only, refused on a locked or approved
run. One transaction: the recalculated values, plate QC and curves commit together, and
saving the run bumps its version, so an approval or lock saved meanwhile makes this a
concurrency conflict. Curves a chemist edited are refitted with these settings; the
result's ``fit_notes`` says how many.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Failure, Result

from cellar.application.auth import AuthContext, require_editor, require_same_workspace
from cellar.application.screening.fit_dose_response import FitOverrides
from cellar.application.screening.readout_calculation_engine import (
    ComputeRunResult,
    ReadoutCalculationEngine,
)
from cellar.application.shared.command import Command
from cellar.application.shared.event_dispatcher import EventDispatcherProtocol
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.screening_assay.repository import RunRepository
from cellar.domain.shared.errors import ConflictError, DomainError, NotFoundError


@dataclass(frozen=True, kw_only=True)
class RecomputeRunCommand(Command):
    workspace_id: uuid.UUID
    run_id: uuid.UUID
    # Run-wide fit constraints for this pass only; never stored.
    fit_overrides: FitOverrides | None = None


class RecomputeRun:
    def __init__(
        self,
        uow: UnitOfWork,
        run_repo: RunRepository,
        calculation_engine: ReadoutCalculationEngine,
        dispatcher: EventDispatcherProtocol,
    ) -> None:
        # The engine works in this use case's unit of work.
        self._uow = uow
        self._run_repo = run_repo
        self._calculation_engine = calculation_engine
        self._dispatcher = dispatcher

    async def __call__(
        self, input: RecomputeRunCommand, auth: AuthContext | None = None
    ) -> Result[ComputeRunResult, DomainError]:
        require_editor(auth)
        require_same_workspace(auth, input.workspace_id)

        async with self._uow:
            run = await self._run_repo.find_by_id_in_workspace(input.workspace_id, input.run_id)
            if run is None:
                return Failure(NotFoundError("Run", str(input.run_id)))
            try:
                run.check_recalculation()
            except ConflictError as exc:
                return Failure(exc)
            await self._run_repo.save(run)
            result = await self._calculation_engine.compute_for_run(
                run.id, workspace_id=input.workspace_id, fit_overrides=input.fit_overrides
            )
            if isinstance(result, Failure):
                return result
            events = await self._uow.commit()

        await self._dispatcher.dispatch_all(events)
        return result
