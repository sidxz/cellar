"""Sample management use cases — aliquot, move, quarantine, dispose."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Failure, Result, Success

from cellar.application.auth import AuthContext, require_editor
from cellar.application.shared.command import Command
from cellar.application.shared.event_dispatcher import EventDispatcherProtocol
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.inventory.repository import SampleRepository, StorageLocationRepository
from cellar.domain.inventory.sample import Sample
from cellar.domain.shared.errors import DomainError, NotFoundError


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


@dataclass(frozen=True, kw_only=True)
class AliquotSampleCommand(Command):
    workspace_id: uuid.UUID
    sample_id: uuid.UUID
    amount: float


@dataclass(frozen=True, kw_only=True)
class MoveSampleCommand(Command):
    workspace_id: uuid.UUID
    sample_id: uuid.UUID
    location_id: uuid.UUID | None = None


@dataclass(frozen=True, kw_only=True)
class QuarantineSampleCommand(Command):
    workspace_id: uuid.UUID
    sample_id: uuid.UUID
    reason: str


@dataclass(frozen=True, kw_only=True)
class ClearQuarantineSampleCommand(Command):
    workspace_id: uuid.UUID
    sample_id: uuid.UUID


@dataclass(frozen=True, kw_only=True)
class DisposeSampleCommand(Command):
    workspace_id: uuid.UUID
    sample_id: uuid.UUID
    reason: str | None = None


# ---------------------------------------------------------------------------
# Use Cases
# ---------------------------------------------------------------------------


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
        self, input: AliquotSampleCommand, auth: AuthContext | None = None
    ) -> Result[Sample, DomainError]:
        require_editor(auth)
        async with self._uow:
            sample = await self._repo.find_by_id_in_workspace(input.workspace_id, input.sample_id)
            if sample is None:
                return Failure(NotFoundError("Sample", str(input.sample_id)))
            sample.aliquot(input.amount)
            await self._repo.save(sample)
            events = await self._uow.commit()

        await self._dispatcher.dispatch_all(events)
        return Success(sample)


class MoveSample:
    def __init__(
        self,
        uow: UnitOfWork,
        repo: SampleRepository,
        location_repo: StorageLocationRepository,
        dispatcher: EventDispatcherProtocol,
    ) -> None:
        self._uow = uow
        self._repo = repo
        self._location_repo = location_repo
        self._dispatcher = dispatcher

    async def __call__(
        self,
        input: MoveSampleCommand,
        auth: AuthContext | None = None,
    ) -> Result[Sample, DomainError]:
        require_editor(auth)
        async with self._uow:
            sample = await self._repo.find_by_id_in_workspace(input.workspace_id, input.sample_id)
            if sample is None:
                return Failure(NotFoundError("Sample", str(input.sample_id)))
            if input.location_id is not None:
                location = await self._location_repo.find_by_id_in_workspace(
                    input.workspace_id, input.location_id
                )
                if location is None:
                    return Failure(NotFoundError("StorageLocation", str(input.location_id)))
            sample.move_to(input.location_id)
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
        input: QuarantineSampleCommand,
        auth: AuthContext | None = None,
    ) -> Result[Sample, DomainError]:
        require_editor(auth)
        async with self._uow:
            sample = await self._repo.find_by_id_in_workspace(input.workspace_id, input.sample_id)
            if sample is None:
                return Failure(NotFoundError("Sample", str(input.sample_id)))
            sample.quarantine(reason=input.reason)
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
        input: ClearQuarantineSampleCommand,
        auth: AuthContext | None = None,
    ) -> Result[Sample, DomainError]:
        require_editor(auth)
        async with self._uow:
            sample = await self._repo.find_by_id_in_workspace(input.workspace_id, input.sample_id)
            if sample is None:
                return Failure(NotFoundError("Sample", str(input.sample_id)))
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
        input: DisposeSampleCommand,
        auth: AuthContext | None = None,
    ) -> Result[Sample, DomainError]:
        require_editor(auth)
        async with self._uow:
            sample = await self._repo.find_by_id_in_workspace(input.workspace_id, input.sample_id)
            if sample is None:
                return Failure(NotFoundError("Sample", str(input.sample_id)))
            sample.dispose(reason=input.reason)
            await self._repo.save(sample)
            events = await self._uow.commit()

        await self._dispatcher.dispatch_all(events)
        return Success(sample)
