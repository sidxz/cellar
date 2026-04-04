"""Sample management use cases — aliquot, move, quarantine, dispose."""

from __future__ import annotations

import uuid

from returns.result import Failure, Result, Success

from chem_vault.application.auth import AuthContext, require_editor, require_same_workspace
from chem_vault.application.shared.event_dispatcher import EventDispatcherProtocol
from chem_vault.application.shared.unit_of_work import UnitOfWork
from chem_vault.domain.inventory.repository import SampleRepository
from chem_vault.domain.inventory.sample import Sample
from chem_vault.domain.shared.errors import DomainError, NotFoundError


class AliquotSample:
    def __init__(
        self,
        uow: UnitOfWork,
        repo: SampleRepository,
        dispatcher: EventDispatcherProtocol,
    ) -> None:
        self._uow = uow
        self._repo = repo
        self._dispatcher = dispatcher

    async def __call__(
        self, sample_id: uuid.UUID, amount: float, auth: AuthContext | None = None
    ) -> Result[Sample, DomainError]:
        require_editor(auth)
        async with self._uow:
            sample = await self._repo.find_by_id(sample_id)
            if sample is None:
                return Failure(NotFoundError("Sample"))
            require_same_workspace(auth, sample.workspace_id)
            sample.aliquot(amount)
            await self._repo.save(sample)
            events = await self._uow.commit()
            await self._dispatcher.dispatch_all(events)
            return Success(sample)


class MoveSample:
    def __init__(
        self,
        uow: UnitOfWork,
        repo: SampleRepository,
        dispatcher: EventDispatcherProtocol,
    ) -> None:
        self._uow = uow
        self._repo = repo
        self._dispatcher = dispatcher

    async def __call__(
        self,
        sample_id: uuid.UUID,
        location_id: uuid.UUID | None,
        auth: AuthContext | None = None,
    ) -> Result[Sample, DomainError]:
        require_editor(auth)
        async with self._uow:
            sample = await self._repo.find_by_id(sample_id)
            if sample is None:
                return Failure(NotFoundError("Sample"))
            require_same_workspace(auth, sample.workspace_id)
            sample.move_to(location_id)
            await self._repo.save(sample)
            events = await self._uow.commit()
            await self._dispatcher.dispatch_all(events)
            return Success(sample)


class QuarantineSample:
    def __init__(
        self,
        uow: UnitOfWork,
        repo: SampleRepository,
        dispatcher: EventDispatcherProtocol,
    ) -> None:
        self._uow = uow
        self._repo = repo
        self._dispatcher = dispatcher

    async def __call__(
        self,
        sample_id: uuid.UUID,
        reason: str,
        auth: AuthContext | None = None,
    ) -> Result[Sample, DomainError]:
        require_editor(auth)
        async with self._uow:
            sample = await self._repo.find_by_id(sample_id)
            if sample is None:
                return Failure(NotFoundError("Sample"))
            require_same_workspace(auth, sample.workspace_id)
            sample.quarantine(reason=reason)
            await self._repo.save(sample)
            events = await self._uow.commit()
            await self._dispatcher.dispatch_all(events)
            return Success(sample)


class ClearQuarantineSample:
    def __init__(
        self,
        uow: UnitOfWork,
        repo: SampleRepository,
        dispatcher: EventDispatcherProtocol,
    ) -> None:
        self._uow = uow
        self._repo = repo
        self._dispatcher = dispatcher

    async def __call__(
        self,
        sample_id: uuid.UUID,
        auth: AuthContext | None = None,
    ) -> Result[Sample, DomainError]:
        require_editor(auth)
        async with self._uow:
            sample = await self._repo.find_by_id(sample_id)
            if sample is None:
                return Failure(NotFoundError("Sample"))
            require_same_workspace(auth, sample.workspace_id)
            sample.clear_quarantine()
            await self._repo.save(sample)
            events = await self._uow.commit()
            await self._dispatcher.dispatch_all(events)
            return Success(sample)


class DisposeSample:
    def __init__(
        self,
        uow: UnitOfWork,
        repo: SampleRepository,
        dispatcher: EventDispatcherProtocol,
    ) -> None:
        self._uow = uow
        self._repo = repo
        self._dispatcher = dispatcher

    async def __call__(
        self,
        sample_id: uuid.UUID,
        reason: str | None = None,
        auth: AuthContext | None = None,
    ) -> Result[Sample, DomainError]:
        require_editor(auth)
        async with self._uow:
            sample = await self._repo.find_by_id(sample_id)
            if sample is None:
                return Failure(NotFoundError("Sample"))
            require_same_workspace(auth, sample.workspace_id)
            sample.dispose(reason=reason)
            await self._repo.save(sample)
            events = await self._uow.commit()
            await self._dispatcher.dispatch_all(events)
            return Success(sample)
