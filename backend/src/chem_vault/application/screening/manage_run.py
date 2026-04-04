"""Run management use cases — start, complete, approve, reject."""

from __future__ import annotations

import uuid

from returns.result import Failure, Result, Success

from chem_vault.application.auth import AuthContext, require_editor, require_same_workspace
from chem_vault.application.shared.event_dispatcher import EventDispatcherProtocol
from chem_vault.application.shared.unit_of_work import UnitOfWork
from chem_vault.domain.screening_assay.repository import RunRepository
from chem_vault.domain.screening_assay.run import Run
from chem_vault.domain.shared.errors import DomainError, NotFoundError


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
        self, run_id: uuid.UUID, auth: AuthContext | None = None
    ) -> Result[Run, DomainError]:
        require_editor(auth)
        async with self._uow:
            run = await self._repo.find_by_id(run_id)
            if run is None:
                return Failure(NotFoundError("Run"))
            require_same_workspace(auth, run.workspace_id)
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
        run_id: uuid.UUID,
        plate_count: int = 0,
        data_point_count: int = 0,
        auth: AuthContext | None = None,
    ) -> Result[Run, DomainError]:
        require_editor(auth)
        async with self._uow:
            run = await self._repo.find_by_id(run_id)
            if run is None:
                return Failure(NotFoundError("Run"))
            require_same_workspace(auth, run.workspace_id)
            run.complete(plate_count=plate_count, data_point_count=data_point_count)
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
        self, run_id: uuid.UUID, auth: AuthContext | None = None
    ) -> Result[Run, DomainError]:
        require_editor(auth)
        async with self._uow:
            run = await self._repo.find_by_id(run_id)
            if run is None:
                return Failure(NotFoundError("Run"))
            require_same_workspace(auth, run.workspace_id)
            run.approve(approved_by=auth.user_id if auth else uuid.uuid4())
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
        run_id: uuid.UUID,
        reason: str,
        auth: AuthContext | None = None,
    ) -> Result[Run, DomainError]:
        require_editor(auth)
        async with self._uow:
            run = await self._repo.find_by_id(run_id)
            if run is None:
                return Failure(NotFoundError("Run"))
            require_same_workspace(auth, run.workspace_id)
            run.reject(rejected_by=auth.user_id if auth else uuid.uuid4(), reason=reason)
            await self._repo.save(run)
            events = await self._uow.commit()
            await self._dispatcher.dispatch_all(events)
            return Success(run)
