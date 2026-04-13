"""Run locking use cases — lock and unlock."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Failure, Result, Success

from chem_vault.application.auth import AuthContext, require_editor
from chem_vault.application.shared.command import Command
from chem_vault.application.shared.event_dispatcher import EventDispatcherProtocol
from chem_vault.application.shared.unit_of_work import UnitOfWork
from chem_vault.domain.screening_assay.repository import RunRepository
from chem_vault.domain.screening_assay.run import Run
from chem_vault.domain.shared.errors import DomainError, NotFoundError


@dataclass(frozen=True, kw_only=True)
class LockRunCommand(Command):
    workspace_id: uuid.UUID
    run_id: uuid.UUID
    reason: str
    locked_by: uuid.UUID


@dataclass(frozen=True, kw_only=True)
class UnlockRunCommand(Command):
    workspace_id: uuid.UUID
    run_id: uuid.UUID
    reason: str
    unlocked_by: uuid.UUID


class LockRun:
    def __init__(
        self,
        uow: UnitOfWork,
        repo: RunRepository,
        dispatcher: EventDispatcherProtocol,
    ) -> None:
        self._uow = uow
        self._repo = repo
        self._dispatcher = dispatcher

    async def __call__(
        self,
        input: LockRunCommand,
        auth: AuthContext | None = None,
    ) -> Result[Run, DomainError]:
        require_editor(auth)
        async with self._uow:
            run = await self._repo.find_by_id_in_workspace(input.workspace_id, input.run_id)
            if run is None:
                return Failure(NotFoundError("Run", str(input.run_id)))
            run.lock(
                locked_by=input.locked_by,
                reason=input.reason,
            )
            await self._repo.save(run)
            events = await self._uow.commit()
            await self._dispatcher.dispatch_all(events)
            return Success(run)


class UnlockRun:
    def __init__(
        self,
        uow: UnitOfWork,
        repo: RunRepository,
        dispatcher: EventDispatcherProtocol,
    ) -> None:
        self._uow = uow
        self._repo = repo
        self._dispatcher = dispatcher

    async def __call__(
        self,
        input: UnlockRunCommand,
        auth: AuthContext | None = None,
    ) -> Result[Run, DomainError]:
        require_editor(auth)
        async with self._uow:
            run = await self._repo.find_by_id_in_workspace(input.workspace_id, input.run_id)
            if run is None:
                return Failure(NotFoundError("Run", str(input.run_id)))
            run.unlock(
                unlocked_by=input.unlocked_by,
                reason=input.reason,
            )
            await self._repo.save(run)
            events = await self._uow.commit()
            await self._dispatcher.dispatch_all(events)
            return Success(run)
