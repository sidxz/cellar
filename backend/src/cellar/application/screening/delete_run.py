"""DeleteRun use case — drafts/in-progress only; cleans curves + readouts."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Failure, Result, Success

from cellar.application.auth import (
    AuthContext,
    require_editor,
    require_same_workspace,
)
from cellar.application.shared.command import Command
from cellar.application.shared.event_dispatcher import EventDispatcherProtocol
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.screening_assay.enums import RunStatus
from cellar.domain.screening_assay.repository import (
    DoseResponseCurveRepository,
    ReadoutDataRepository,
    RunRepository,
)
from cellar.domain.shared.errors import (
    ConflictError,
    DomainError,
    NotFoundError,
)


@dataclass(frozen=True, kw_only=True)
class DeleteRunCommand(Command):
    workspace_id: uuid.UUID
    run_id: uuid.UUID


class DeleteRun:
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
        input: DeleteRunCommand,
        auth: AuthContext | None = None,
    ) -> Result[None, DomainError]:
        require_editor(auth)
        require_same_workspace(auth, input.workspace_id)

        async with self._uow:
            run = await self._run_repo.find_by_id_in_workspace(input.workspace_id, input.run_id)
            if run is None:
                return Failure(NotFoundError("Run", str(input.run_id)))

            if run.is_locked:
                return Failure(ConflictError("Cannot delete a locked run"))

            # Only drafts and in-progress runs may be deleted; terminal states have audit trails.
            if run.status not in (RunStatus.DRAFT, RunStatus.IN_PROGRESS):
                return Failure(
                    ConflictError(
                        f"Cannot delete a run in status '{run.status.value}'. "
                        "Only draft or in-progress runs can be deleted."
                    )
                )

            # Order: curves -> readouts -> run (no FK cascade on these tables).
            await self._curve_repo.delete_by_run(input.workspace_id, input.run_id)
            await self._readout_data_repo.delete_for_run(input.workspace_id, input.run_id)
            await self._run_repo.delete(input.workspace_id, input.run_id)

            events = await self._uow.commit()

        await self._dispatcher.dispatch_all(events)
        return Success(None)
