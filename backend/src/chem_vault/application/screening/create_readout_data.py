"""CreateReadoutData use case with DataLockGuard protection."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Failure, Result, Success

from chem_vault.application.auth import AuthContext, require_editor
from chem_vault.application.shared.command import Command
from chem_vault.application.shared.event_dispatcher import EventDispatcherProtocol
from chem_vault.application.shared.unit_of_work import UnitOfWork
from chem_vault.domain.screening_assay.data_lock_guard import DataLockGuard
from chem_vault.domain.screening_assay.readout_data import ReadoutData
from chem_vault.domain.screening_assay.repository import ReadoutDataRepository, RunRepository
from chem_vault.domain.shared.enums import Qualifier
from chem_vault.domain.shared.errors import DomainError, NotFoundError
from chem_vault.domain.shared.value_objects import QualifiedValue


@dataclass(frozen=True, kw_only=True)
class CreateReadoutDataCommand(Command):
    workspace_id: uuid.UUID
    run_id: uuid.UUID
    well_id: uuid.UUID | None = None
    molecule_id: uuid.UUID
    batch_id: uuid.UUID
    readout_definition_id: uuid.UUID
    value_numeric: float | None = None
    value_qualifier: str | None = None
    value_text: str | None = None
    is_outlier: bool = False


class CreateReadoutData:
    def __init__(
        self,
        uow: UnitOfWork,
        repo: ReadoutDataRepository,
        guard: DataLockGuard,
        dispatcher: EventDispatcherProtocol,
        run_repo: RunRepository | None = None,
    ) -> None:
        self._uow = uow
        self._repo = repo
        self._guard = guard
        self._dispatcher = dispatcher
        self._run_repo = run_repo

    async def __call__(
        self, input: CreateReadoutDataCommand, auth: AuthContext | None = None
    ) -> Result[ReadoutData, DomainError]:
        require_editor(auth)

        async with self._uow:
            # Verify run belongs to this workspace
            if self._run_repo is not None:
                run = await self._run_repo.find_by_id_in_workspace(
                    input.workspace_id, input.run_id
                )
                if run is None:
                    return Failure(NotFoundError("Run", str(input.run_id)))

            # Guard against locked runs
            try:
                await self._guard.guard_write(input.workspace_id, input.run_id)
            except DomainError as exc:
                return Failure(exc)

            value = None
            if input.value_numeric is not None:
                qualifier = (
                    Qualifier(input.value_qualifier)
                    if input.value_qualifier
                    else Qualifier.EQUAL
                )
                value = QualifiedValue(value=input.value_numeric, qualifier=qualifier)

            readout = ReadoutData(
                workspace_id=input.workspace_id,
                run_id=input.run_id,
                well_id=input.well_id,
                molecule_id=input.molecule_id,
                batch_id=input.batch_id,
                readout_definition_id=input.readout_definition_id,
                value=value,
                value_text=input.value_text,
                is_outlier=input.is_outlier,
            )
            await self._repo.save(readout)
            events = await self._uow.commit()
            await self._dispatcher.dispatch_all(events)
            return Success(readout)
