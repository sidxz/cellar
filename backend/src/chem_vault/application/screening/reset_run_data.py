"""ResetRunData — wipe a run's plates/wells/readouts/curves/QC.

This is the destructive escape hatch for a chemist who needs to redo
their run from scratch (e.g. the first imported file had the wrong
column mapping and every subsequent re-import is now 100% conflicts
under the non-destructive import semantics).

What gets cleared:
    - dose_response_curves
    - readout_data
    - plates (cascades to wells via FK)
    - run.qc_metrics

What is preserved:
    - the run row itself
    - run metadata (name, status, plate_format, protocol_id, operator,
      notes, conditions, etc.)
    - any uploaded file attachments (audit artifacts)

Only DRAFT and IN_PROGRESS runs may be reset. Locked runs are rejected.
Approved/rejected/completed runs have audit trails and cannot be reset.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Failure, Result, Success

from chem_vault.application.auth import (
    AuthContext,
    require_editor,
    require_same_workspace,
)
from chem_vault.application.shared.command import Command
from chem_vault.application.shared.event_dispatcher import EventDispatcherProtocol
from chem_vault.application.shared.unit_of_work import UnitOfWork
from chem_vault.domain.screening_assay.enums import RunStatus
from chem_vault.domain.screening_assay.repository import (
    DoseResponseCurveRepository,
    ReadoutDataRepository,
    RunRepository,
)
from chem_vault.domain.shared.errors import (
    ConflictError,
    DomainError,
    NotFoundError,
)


@dataclass(frozen=True, kw_only=True)
class ResetRunDataCommand(Command):
    workspace_id: uuid.UUID
    run_id: uuid.UUID


@dataclass(frozen=True)
class ResetRunDataResult:
    plates_deleted: int
    wells_deleted: int
    readouts_deleted: int
    curves_deleted: int


class ResetRunData:
    def __init__(
        self,
        uow: UnitOfWork,
        run_repo: RunRepository,
        readout_data_repo: ReadoutDataRepository,
        curve_repo: DoseResponseCurveRepository,
        dispatcher: EventDispatcherProtocol,
    ) -> None:
        self._uow = uow
        self._run_repo = run_repo
        self._readout_data_repo = readout_data_repo
        self._curve_repo = curve_repo
        self._dispatcher = dispatcher

    async def __call__(
        self,
        input: ResetRunDataCommand,
        auth: AuthContext | None = None,
    ) -> Result[ResetRunDataResult, DomainError]:
        require_editor(auth)
        require_same_workspace(auth, input.workspace_id)

        async with self._uow:
            run = await self._run_repo.find_by_id_in_workspace(
                input.workspace_id, input.run_id
            )
            if run is None:
                return Failure(NotFoundError("Run", str(input.run_id)))

            if run.is_locked:
                return Failure(
                    ConflictError("Cannot reset data on a locked run")
                )
            if run.status not in (RunStatus.DRAFT, RunStatus.IN_PROGRESS):
                return Failure(
                    ConflictError(
                        f"Cannot reset a run in status '{run.status.value}'. "
                        "Only draft or in-progress runs can be reset."
                    )
                )

            plates_before = len(run.plates)
            wells_before = len(run.wells)

            # Cleanup order: curves → readouts → plates (cascade wells).
            # Curves and readouts have no FK cascade from run; plates do.
            existing_curves = await self._curve_repo.find_by_run(
                input.workspace_id, input.run_id
            )
            curves_deleted = len(existing_curves)
            await self._curve_repo.delete_by_run(
                input.workspace_id, input.run_id
            )
            readouts_deleted = await self._readout_data_repo.delete_for_run(
                input.workspace_id, input.run_id
            )
            run.reset_data(
                readouts_deleted=readouts_deleted,
                curves_deleted=curves_deleted,
            )
            await self._run_repo.save(run)

            events = await self._uow.commit()

        await self._dispatcher.dispatch_all(events)
        return Success(
            ResetRunDataResult(
                plates_deleted=plates_before,
                wells_deleted=wells_before,
                readouts_deleted=readouts_deleted,
                curves_deleted=curves_deleted,
            )
        )
