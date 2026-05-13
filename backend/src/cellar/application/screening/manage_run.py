"""Run management use cases — start, complete, approve, reject."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Failure, Result, Success

from cellar.application.auth import AuthContext, require_editor
from cellar.application.shared.command import Command
from cellar.application.shared.event_dispatcher import EventDispatcherProtocol
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.screening_assay.repository import RunRepository
from cellar.domain.screening_assay.run import Run
from cellar.domain.shared.errors import AuthorizationError, DomainError, NotFoundError


@dataclass(frozen=True, kw_only=True)
class StartRunCommand(Command):
    workspace_id: uuid.UUID
    run_id: uuid.UUID


@dataclass(frozen=True, kw_only=True)
class CompleteRunCommand(Command):
    workspace_id: uuid.UUID
    run_id: uuid.UUID
    plate_count: int = 0
    data_point_count: int = 0


@dataclass(frozen=True, kw_only=True)
class ApproveRunCommand(Command):
    workspace_id: uuid.UUID
    run_id: uuid.UUID


@dataclass(frozen=True, kw_only=True)
class RejectRunCommand(Command):
    workspace_id: uuid.UUID
    run_id: uuid.UUID
    reason: str


class StartRun:
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
        self, input: StartRunCommand, auth: AuthContext | None = None
    ) -> Result[Run, DomainError]:
        require_editor(auth)
        async with self._uow:
            run = await self._repo.find_by_id_in_workspace(input.workspace_id, input.run_id)
            if run is None:
                return Failure(NotFoundError("Run", str(input.run_id)))
            run.start()
            await self._repo.save(run)
            events = await self._uow.commit()

        await self._dispatcher.dispatch_all(events)
        return Success(run)


class CompleteRun:
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
        input: CompleteRunCommand,
        auth: AuthContext | None = None,
    ) -> Result[Run, DomainError]:
        require_editor(auth)
        async with self._uow:
            run = await self._repo.find_by_id_in_workspace(input.workspace_id, input.run_id)
            if run is None:
                return Failure(NotFoundError("Run", str(input.run_id)))
            run.complete(plate_count=input.plate_count, data_point_count=input.data_point_count)
            await self._repo.save(run)
            events = await self._uow.commit()

        await self._dispatcher.dispatch_all(events)
        return Success(run)


class ApproveRun:
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
        self, input: ApproveRunCommand, auth: AuthContext | None = None
    ) -> Result[Run, DomainError]:
        if auth is None:
            return Failure(AuthorizationError("Authentication required to approve a run"))
        require_editor(auth)
        async with self._uow:
            run = await self._repo.find_by_id_in_workspace(input.workspace_id, input.run_id)
            if run is None:
                return Failure(NotFoundError("Run", str(input.run_id)))
            run.approve(approved_by=auth.user_id)
            await self._repo.save(run)
            events = await self._uow.commit()

        await self._dispatcher.dispatch_all(events)
        return Success(run)


class RejectRun:
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
        input: RejectRunCommand,
        auth: AuthContext | None = None,
    ) -> Result[Run, DomainError]:
        if auth is None:
            return Failure(AuthorizationError("Authentication required to reject a run"))
        require_editor(auth)
        async with self._uow:
            run = await self._repo.find_by_id_in_workspace(input.workspace_id, input.run_id)
            if run is None:
                return Failure(NotFoundError("Run", str(input.run_id)))
            run.reject(rejected_by=auth.user_id, reason=input.reason)
            await self._repo.save(run)
            events = await self._uow.commit()

        await self._dispatcher.dispatch_all(events)
        return Success(run)
