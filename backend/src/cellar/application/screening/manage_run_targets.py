"""Run-target association use cases — add / remove a target on a run.

Run targets are independent per run. Adding one rolls up to the run's protocol
via the read-time effective-target union (no write to the protocol); removing
the last run reference auto-prunes inherited protocol targets. See
``docs/superpowers/specs/2026-06-05-run-protocol-multi-targets-design.md``.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Failure, Result, Success

from cellar.application.auth import AuthContext, require_editor
from cellar.application.shared.command import Command
from cellar.application.shared.event_dispatcher import EventDispatcherProtocol
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.screening_assay.repository import RunRepository
from cellar.domain.shared.errors import ConflictError, DomainError, NotFoundError


@dataclass(frozen=True, kw_only=True)
class AddRunTargetCommand(Command):
    workspace_id: uuid.UUID
    run_id: uuid.UUID
    target_id: uuid.UUID


@dataclass(frozen=True, kw_only=True)
class RemoveRunTargetCommand(Command):
    workspace_id: uuid.UUID
    run_id: uuid.UUID
    target_id: uuid.UUID


class AddRunTarget:
    """Attach a target to a run (idempotent). Blocked when the run is locked."""

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
        self, input: AddRunTargetCommand, auth: AuthContext | None = None
    ) -> Result[None, DomainError]:
        require_editor(auth)
        async with self._uow:
            run = await self._repo.find_by_id_in_workspace(input.workspace_id, input.run_id)
            if run is None:
                return Failure(NotFoundError("Run", str(input.run_id)))
            if run.is_locked:
                return Failure(ConflictError("Cannot modify a locked run — unlock it first"))
            await self._repo.add_target(input.workspace_id, input.run_id, input.target_id)
            events = await self._uow.commit()

        await self._dispatcher.dispatch_all(events)
        return Success(None)


class RemoveRunTarget:
    """Remove a target from a run. Blocked when the run is locked."""

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
        self, input: RemoveRunTargetCommand, auth: AuthContext | None = None
    ) -> Result[None, DomainError]:
        require_editor(auth)
        async with self._uow:
            run = await self._repo.find_by_id_in_workspace(input.workspace_id, input.run_id)
            if run is None:
                return Failure(NotFoundError("Run", str(input.run_id)))
            if run.is_locked:
                return Failure(ConflictError("Cannot modify a locked run — unlock it first"))
            await self._repo.remove_target(input.workspace_id, input.run_id, input.target_id)
            events = await self._uow.commit()

        await self._dispatcher.dispatch_all(events)
        return Success(None)
