"""SampleRequest use cases — lifecycle management for compound material requests."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Failure, Result, Success

from chem_vault.application.auth import AuthContext, require_editor, require_same_workspace
from chem_vault.application.shared.command import Command
from chem_vault.application.shared.event_dispatcher import EventDispatcherProtocol
from chem_vault.application.shared.query import Query
from chem_vault.application.shared.unit_of_work import UnitOfWork
from chem_vault.domain.inventory.enums import RequestPriority, SampleRequestStatus
from chem_vault.domain.inventory.repository import SampleRequestRepository
from chem_vault.domain.inventory.sample_request import SampleRequest
from chem_vault.domain.shared.enums import AmountUnit
from chem_vault.application.shared.sentinel import UNSET
from chem_vault.domain.shared.errors import DomainError, NotFoundError, ValidationError
from chem_vault.domain.shared.value_objects import Amount


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


@dataclass(frozen=True, kw_only=True)
class CreateSampleRequestCommand(Command):
    workspace_id: uuid.UUID
    requester_id: uuid.UUID
    molecule_id: uuid.UUID
    batch_id: uuid.UUID | None = None
    amount_value: float
    amount_unit: str
    purpose: str
    priority: str = "routine"


@dataclass(frozen=True, kw_only=True)
class ApproveSampleRequestCommand(Command):
    request_id: uuid.UUID
    assigned_to: uuid.UUID | None = None


@dataclass(frozen=True, kw_only=True)
class RejectSampleRequestCommand(Command):
    request_id: uuid.UUID
    reason: str


@dataclass(frozen=True, kw_only=True)
class FulfillSampleRequestCommand(Command):
    request_id: uuid.UUID
    sample_id: uuid.UUID


@dataclass(frozen=True, kw_only=True)
class CancelSampleRequestCommand(Command):
    request_id: uuid.UUID


@dataclass(frozen=True, kw_only=True)
class StartPreparingSampleRequestCommand(Command):
    request_id: uuid.UUID


@dataclass(frozen=True, kw_only=True)
class UpdateSampleRequestCommand(Command):
    request_id: uuid.UUID
    purpose: str | object = UNSET
    priority: str | object = UNSET
    amount_value: float | object = UNSET
    amount_unit: str | object = UNSET


# ---------------------------------------------------------------------------
# Queries
# ---------------------------------------------------------------------------


@dataclass(frozen=True, kw_only=True)
class GetSampleRequestQuery(Query):
    request_id: uuid.UUID


@dataclass(frozen=True, kw_only=True)
class ListSampleRequestsQuery(Query):
    workspace_id: uuid.UUID
    status: str | None = None


# ---------------------------------------------------------------------------
# Use Cases
# ---------------------------------------------------------------------------


class CreateSampleRequest:
    def __init__(
        self,
        uow: UnitOfWork,
        repo: SampleRequestRepository,
        dispatcher: EventDispatcherProtocol,
    ) -> None:
        self._uow = uow
        self._repo = repo
        self._dispatcher = dispatcher

    async def __call__(
        self, input: CreateSampleRequestCommand, auth: AuthContext | None = None
    ) -> Result[SampleRequest, DomainError]:
        require_editor(auth)
        async with self._uow:
            requested_amount = Amount(
                value=input.amount_value,
                unit=AmountUnit(input.amount_unit),
            )
            request = SampleRequest.create(
                workspace_id=input.workspace_id,
                requester_id=input.requester_id,
                molecule_id=input.molecule_id,
                batch_id=input.batch_id,
                requested_amount=requested_amount,
                purpose=input.purpose,
                priority=RequestPriority(input.priority),
            )
            await self._repo.save(request)
            events = await self._uow.commit()
            await self._dispatcher.dispatch_all(events)
            return Success(request)


class GetSampleRequest:
    def __init__(self, uow: UnitOfWork, repo: SampleRequestRepository) -> None:
        self._uow = uow
        self._repo = repo

    async def __call__(
        self, input: GetSampleRequestQuery, auth: AuthContext | None = None
    ) -> Result[SampleRequest, DomainError]:
        async with self._uow:
            request = await self._repo.find_by_id(input.request_id)
            if request is None:
                return Failure(NotFoundError("SampleRequest", str(input.request_id)))
            require_same_workspace(auth, request.workspace_id)
            return Success(request)


class ListSampleRequests:
    def __init__(self, uow: UnitOfWork, repo: SampleRequestRepository) -> None:
        self._uow = uow
        self._repo = repo

    async def __call__(
        self, input: ListSampleRequestsQuery, auth: AuthContext | None = None
    ) -> Result[list[SampleRequest], DomainError]:
        async with self._uow:
            requests = await self._repo.find_by_workspace(
                input.workspace_id, status=input.status
            )
            return Success(requests)


class ApproveSampleRequest:
    def __init__(
        self,
        uow: UnitOfWork,
        repo: SampleRequestRepository,
        dispatcher: EventDispatcherProtocol,
    ) -> None:
        self._uow = uow
        self._repo = repo
        self._dispatcher = dispatcher

    async def __call__(
        self, input: ApproveSampleRequestCommand, auth: AuthContext | None = None
    ) -> Result[SampleRequest, DomainError]:
        require_editor(auth)
        async with self._uow:
            request = await self._repo.find_by_id(input.request_id)
            if request is None:
                return Failure(NotFoundError("SampleRequest", str(input.request_id)))
            require_same_workspace(auth, request.workspace_id)
            request.approve(assigned_to=input.assigned_to)
            await self._repo.save(request)
            events = await self._uow.commit()
            await self._dispatcher.dispatch_all(events)
            return Success(request)


class RejectSampleRequest:
    def __init__(
        self,
        uow: UnitOfWork,
        repo: SampleRequestRepository,
        dispatcher: EventDispatcherProtocol,
    ) -> None:
        self._uow = uow
        self._repo = repo
        self._dispatcher = dispatcher

    async def __call__(
        self, input: RejectSampleRequestCommand, auth: AuthContext | None = None
    ) -> Result[SampleRequest, DomainError]:
        require_editor(auth)
        async with self._uow:
            request = await self._repo.find_by_id(input.request_id)
            if request is None:
                return Failure(NotFoundError("SampleRequest", str(input.request_id)))
            require_same_workspace(auth, request.workspace_id)
            request.reject(reason=input.reason)
            await self._repo.save(request)
            events = await self._uow.commit()
            await self._dispatcher.dispatch_all(events)
            return Success(request)


class FulfillSampleRequest:
    def __init__(
        self,
        uow: UnitOfWork,
        repo: SampleRequestRepository,
        dispatcher: EventDispatcherProtocol,
    ) -> None:
        self._uow = uow
        self._repo = repo
        self._dispatcher = dispatcher

    async def __call__(
        self, input: FulfillSampleRequestCommand, auth: AuthContext | None = None
    ) -> Result[SampleRequest, DomainError]:
        require_editor(auth)
        async with self._uow:
            request = await self._repo.find_by_id(input.request_id)
            if request is None:
                return Failure(NotFoundError("SampleRequest", str(input.request_id)))
            require_same_workspace(auth, request.workspace_id)
            request.fulfill(sample_id=input.sample_id)
            await self._repo.save(request)
            events = await self._uow.commit()
            await self._dispatcher.dispatch_all(events)
            return Success(request)


class CancelSampleRequest:
    def __init__(
        self,
        uow: UnitOfWork,
        repo: SampleRequestRepository,
        dispatcher: EventDispatcherProtocol,
    ) -> None:
        self._uow = uow
        self._repo = repo
        self._dispatcher = dispatcher

    async def __call__(
        self, input: CancelSampleRequestCommand, auth: AuthContext | None = None
    ) -> Result[SampleRequest, DomainError]:
        require_editor(auth)
        async with self._uow:
            request = await self._repo.find_by_id(input.request_id)
            if request is None:
                return Failure(NotFoundError("SampleRequest", str(input.request_id)))
            require_same_workspace(auth, request.workspace_id)
            request.cancel()
            await self._repo.save(request)
            events = await self._uow.commit()
            await self._dispatcher.dispatch_all(events)
            return Success(request)


class StartPreparingSampleRequest:
    def __init__(
        self,
        uow: UnitOfWork,
        repo: SampleRequestRepository,
        dispatcher: EventDispatcherProtocol,
    ) -> None:
        self._uow = uow
        self._repo = repo
        self._dispatcher = dispatcher

    async def __call__(
        self, input: StartPreparingSampleRequestCommand, auth: AuthContext | None = None
    ) -> Result[SampleRequest, DomainError]:
        require_editor(auth)
        async with self._uow:
            request = await self._repo.find_by_id(input.request_id)
            if request is None:
                return Failure(NotFoundError("SampleRequest", str(input.request_id)))
            require_same_workspace(auth, request.workspace_id)
            request.start_preparing()
            await self._repo.save(request)
            events = await self._uow.commit()
            await self._dispatcher.dispatch_all(events)
            return Success(request)


class UpdateSampleRequest:
    def __init__(
        self,
        uow: UnitOfWork,
        repo: SampleRequestRepository,
        dispatcher: EventDispatcherProtocol,
    ) -> None:
        self._uow = uow
        self._repo = repo
        self._dispatcher = dispatcher

    async def __call__(
        self, input: UpdateSampleRequestCommand, auth: AuthContext | None = None
    ) -> Result[SampleRequest, DomainError]:
        require_editor(auth)
        async with self._uow:
            request = await self._repo.find_by_id(input.request_id)
            if request is None:
                return Failure(NotFoundError("SampleRequest", str(input.request_id)))
            require_same_workspace(auth, request.workspace_id)

            if request.status != SampleRequestStatus.SUBMITTED:
                return Failure(ValidationError("Can only update submitted sample requests"))

            if input.purpose is not UNSET:
                request.purpose = input.purpose
            if input.priority is not UNSET:
                request.priority = RequestPriority(input.priority)

            if input.amount_value is not UNSET or input.amount_unit is not UNSET:
                new_value = input.amount_value if input.amount_value is not UNSET else request.requested_amount.value
                new_unit = input.amount_unit if input.amount_unit is not UNSET else request.requested_amount.unit.value
                request.requested_amount = Amount(value=new_value, unit=AmountUnit(new_unit))

            await self._repo.save(request)
            events = await self._uow.commit()
            await self._dispatcher.dispatch_all(events)
            return Success(request)
