"""SynthesisRequest use cases — 10-state lifecycle management for compound synthesis requests."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Failure, Result, Success

from chem_vault.application.auth import AuthContext, require_editor, require_same_workspace
from chem_vault.application.shared.command import Command
from chem_vault.application.shared.event_dispatcher import EventDispatcherProtocol
from chem_vault.application.shared.query import Query
from chem_vault.application.shared.unit_of_work import UnitOfWork
from chem_vault.domain.inventory.enums import FeasibilityStatus, RequestPriority
from chem_vault.domain.inventory.repository import SynthesisRequestRepository
from chem_vault.domain.inventory.synthesis_request import SynthesisRequest
from chem_vault.domain.shared.enums import AmountUnit, AssignmentType
from chem_vault.domain.shared.errors import DomainError, NotFoundError
from chem_vault.domain.shared.value_objects import Amount, SynthesisAssignment


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


@dataclass(frozen=True, kw_only=True)
class CreateSynthesisRequestCommand(Command):
    workspace_id: uuid.UUID
    requester_id: uuid.UUID
    molecule_id: uuid.UUID
    amount_value: float
    amount_unit: str
    purpose: str
    priority: str = "routine"
    target_purity: float | None = None
    project_id: uuid.UUID | None = None
    parent_request_id: uuid.UUID | None = None


@dataclass(frozen=True, kw_only=True)
class SubmitSynthesisRequestCommand(Command):
    request_id: uuid.UUID


@dataclass(frozen=True, kw_only=True)
class ApproveSynthesisRequestCommand(Command):
    request_id: uuid.UUID
    approved_by: uuid.UUID


@dataclass(frozen=True, kw_only=True)
class RejectSynthesisRequestCommand(Command):
    request_id: uuid.UUID
    reason: str
    rejected_by: uuid.UUID


@dataclass(frozen=True, kw_only=True)
class AssignSynthesisRequestCommand(Command):
    request_id: uuid.UUID
    assignment_type: str
    assigned_to: uuid.UUID | None = None
    assigned_org_id: uuid.UUID | None = None


@dataclass(frozen=True, kw_only=True)
class StartSynthesisCommand(Command):
    request_id: uuid.UUID
    proposed_route_id: uuid.UUID | None = None


@dataclass(frozen=True, kw_only=True)
class FlagInfeasibleCommand(Command):
    request_id: uuid.UUID
    feasibility_status: str
    feasibility_notes: str | None = None


@dataclass(frozen=True, kw_only=True)
class CompleteSynthesisCommand(Command):
    request_id: uuid.UUID
    actual_cost_value: float | None = None
    actual_cost_unit: str | None = None


@dataclass(frozen=True, kw_only=True)
class FulfillSynthesisRequestCommand(Command):
    request_id: uuid.UUID
    batch_id: uuid.UUID


@dataclass(frozen=True, kw_only=True)
class FailSynthesisCommand(Command):
    request_id: uuid.UUID
    reason: str


@dataclass(frozen=True, kw_only=True)
class CancelSynthesisRequestCommand(Command):
    request_id: uuid.UUID


# ---------------------------------------------------------------------------
# Queries
# ---------------------------------------------------------------------------


@dataclass(frozen=True, kw_only=True)
class GetSynthesisRequestQuery(Query):
    request_id: uuid.UUID


@dataclass(frozen=True, kw_only=True)
class ListSynthesisRequestsQuery(Query):
    workspace_id: uuid.UUID
    status: str | None = None
    molecule_id: uuid.UUID | None = None


# ---------------------------------------------------------------------------
# Use Cases
# ---------------------------------------------------------------------------


class CreateSynthesisRequest:
    def __init__(
        self,
        uow: UnitOfWork,
        repo: SynthesisRequestRepository,
        dispatcher: EventDispatcherProtocol,
    ) -> None:
        self._uow = uow
        self._repo = repo
        self._dispatcher = dispatcher

    async def __call__(
        self, input: CreateSynthesisRequestCommand, auth: AuthContext | None = None
    ) -> Result[SynthesisRequest, DomainError]:
        require_editor(auth)
        async with self._uow:
            requested_amount = Amount(
                value=input.amount_value,
                unit=AmountUnit(input.amount_unit),
            )
            request = SynthesisRequest.create(
                workspace_id=input.workspace_id,
                requester_id=input.requester_id,
                molecule_id=input.molecule_id,
                requested_amount=requested_amount,
                purpose=input.purpose,
                priority=RequestPriority(input.priority),
                target_purity=input.target_purity,
                project_id=input.project_id,
                parent_request_id=input.parent_request_id,
            )
            await self._repo.save(request)
            events = await self._uow.commit()
            await self._dispatcher.dispatch_all(events)
            return Success(request)


class SubmitSynthesisRequest:
    def __init__(
        self,
        uow: UnitOfWork,
        repo: SynthesisRequestRepository,
        dispatcher: EventDispatcherProtocol,
    ) -> None:
        self._uow = uow
        self._repo = repo
        self._dispatcher = dispatcher

    async def __call__(
        self, input: SubmitSynthesisRequestCommand, auth: AuthContext | None = None
    ) -> Result[SynthesisRequest, DomainError]:
        require_editor(auth)
        async with self._uow:
            request = await self._repo.find_by_id(input.request_id)
            if request is None:
                return Failure(NotFoundError("SynthesisRequest", str(input.request_id)))
            require_same_workspace(auth, request.workspace_id)
            request.submit()
            await self._repo.save(request)
            events = await self._uow.commit()
            await self._dispatcher.dispatch_all(events)
            return Success(request)


class ApproveSynthesisRequest:
    def __init__(
        self,
        uow: UnitOfWork,
        repo: SynthesisRequestRepository,
        dispatcher: EventDispatcherProtocol,
    ) -> None:
        self._uow = uow
        self._repo = repo
        self._dispatcher = dispatcher

    async def __call__(
        self, input: ApproveSynthesisRequestCommand, auth: AuthContext | None = None
    ) -> Result[SynthesisRequest, DomainError]:
        require_editor(auth)
        async with self._uow:
            request = await self._repo.find_by_id(input.request_id)
            if request is None:
                return Failure(NotFoundError("SynthesisRequest", str(input.request_id)))
            require_same_workspace(auth, request.workspace_id)
            request.approve(approved_by=input.approved_by)
            await self._repo.save(request)
            events = await self._uow.commit()
            await self._dispatcher.dispatch_all(events)
            return Success(request)


class RejectSynthesisRequest:
    def __init__(
        self,
        uow: UnitOfWork,
        repo: SynthesisRequestRepository,
        dispatcher: EventDispatcherProtocol,
    ) -> None:
        self._uow = uow
        self._repo = repo
        self._dispatcher = dispatcher

    async def __call__(
        self, input: RejectSynthesisRequestCommand, auth: AuthContext | None = None
    ) -> Result[SynthesisRequest, DomainError]:
        require_editor(auth)
        async with self._uow:
            request = await self._repo.find_by_id(input.request_id)
            if request is None:
                return Failure(NotFoundError("SynthesisRequest", str(input.request_id)))
            require_same_workspace(auth, request.workspace_id)
            request.reject(reason=input.reason, rejected_by=input.rejected_by)
            await self._repo.save(request)
            events = await self._uow.commit()
            await self._dispatcher.dispatch_all(events)
            return Success(request)


class AssignSynthesisRequest:
    def __init__(
        self,
        uow: UnitOfWork,
        repo: SynthesisRequestRepository,
        dispatcher: EventDispatcherProtocol,
    ) -> None:
        self._uow = uow
        self._repo = repo
        self._dispatcher = dispatcher

    async def __call__(
        self, input: AssignSynthesisRequestCommand, auth: AuthContext | None = None
    ) -> Result[SynthesisRequest, DomainError]:
        require_editor(auth)
        async with self._uow:
            request = await self._repo.find_by_id(input.request_id)
            if request is None:
                return Failure(NotFoundError("SynthesisRequest", str(input.request_id)))
            require_same_workspace(auth, request.workspace_id)
            assignment = SynthesisAssignment(
                assignment_type=AssignmentType(input.assignment_type),
                assigned_to=input.assigned_to,
                assigned_org_id=input.assigned_org_id,
            )
            request.assign(assignment)
            await self._repo.save(request)
            events = await self._uow.commit()
            await self._dispatcher.dispatch_all(events)
            return Success(request)


class StartSynthesis:
    def __init__(
        self,
        uow: UnitOfWork,
        repo: SynthesisRequestRepository,
        dispatcher: EventDispatcherProtocol,
    ) -> None:
        self._uow = uow
        self._repo = repo
        self._dispatcher = dispatcher

    async def __call__(
        self, input: StartSynthesisCommand, auth: AuthContext | None = None
    ) -> Result[SynthesisRequest, DomainError]:
        require_editor(auth)
        async with self._uow:
            request = await self._repo.find_by_id(input.request_id)
            if request is None:
                return Failure(NotFoundError("SynthesisRequest", str(input.request_id)))
            require_same_workspace(auth, request.workspace_id)
            request.start(proposed_route_id=input.proposed_route_id)
            await self._repo.save(request)
            events = await self._uow.commit()
            await self._dispatcher.dispatch_all(events)
            return Success(request)


class FlagInfeasible:
    def __init__(
        self,
        uow: UnitOfWork,
        repo: SynthesisRequestRepository,
        dispatcher: EventDispatcherProtocol,
    ) -> None:
        self._uow = uow
        self._repo = repo
        self._dispatcher = dispatcher

    async def __call__(
        self, input: FlagInfeasibleCommand, auth: AuthContext | None = None
    ) -> Result[SynthesisRequest, DomainError]:
        require_editor(auth)
        async with self._uow:
            request = await self._repo.find_by_id(input.request_id)
            if request is None:
                return Failure(NotFoundError("SynthesisRequest", str(input.request_id)))
            require_same_workspace(auth, request.workspace_id)
            request.flag_infeasible(
                feasibility_status=FeasibilityStatus(input.feasibility_status),
                feasibility_notes=input.feasibility_notes,
            )
            await self._repo.save(request)
            events = await self._uow.commit()
            await self._dispatcher.dispatch_all(events)
            return Success(request)


class CompleteSynthesis:
    def __init__(
        self,
        uow: UnitOfWork,
        repo: SynthesisRequestRepository,
        dispatcher: EventDispatcherProtocol,
    ) -> None:
        self._uow = uow
        self._repo = repo
        self._dispatcher = dispatcher

    async def __call__(
        self, input: CompleteSynthesisCommand, auth: AuthContext | None = None
    ) -> Result[SynthesisRequest, DomainError]:
        require_editor(auth)
        async with self._uow:
            request = await self._repo.find_by_id(input.request_id)
            if request is None:
                return Failure(NotFoundError("SynthesisRequest", str(input.request_id)))
            require_same_workspace(auth, request.workspace_id)
            actual_cost = None
            if input.actual_cost_value is not None and input.actual_cost_unit is not None:
                actual_cost = Amount(
                    value=input.actual_cost_value,
                    unit=AmountUnit(input.actual_cost_unit),
                )
            request.complete_synthesis(actual_cost=actual_cost)
            await self._repo.save(request)
            events = await self._uow.commit()
            await self._dispatcher.dispatch_all(events)
            return Success(request)


class FulfillSynthesisRequest:
    def __init__(
        self,
        uow: UnitOfWork,
        repo: SynthesisRequestRepository,
        dispatcher: EventDispatcherProtocol,
    ) -> None:
        self._uow = uow
        self._repo = repo
        self._dispatcher = dispatcher

    async def __call__(
        self, input: FulfillSynthesisRequestCommand, auth: AuthContext | None = None
    ) -> Result[SynthesisRequest, DomainError]:
        require_editor(auth)
        async with self._uow:
            request = await self._repo.find_by_id(input.request_id)
            if request is None:
                return Failure(NotFoundError("SynthesisRequest", str(input.request_id)))
            require_same_workspace(auth, request.workspace_id)
            request.fulfill(batch_id=input.batch_id)
            await self._repo.save(request)
            events = await self._uow.commit()
            await self._dispatcher.dispatch_all(events)
            return Success(request)


class FailSynthesis:
    def __init__(
        self,
        uow: UnitOfWork,
        repo: SynthesisRequestRepository,
        dispatcher: EventDispatcherProtocol,
    ) -> None:
        self._uow = uow
        self._repo = repo
        self._dispatcher = dispatcher

    async def __call__(
        self, input: FailSynthesisCommand, auth: AuthContext | None = None
    ) -> Result[SynthesisRequest, DomainError]:
        require_editor(auth)
        async with self._uow:
            request = await self._repo.find_by_id(input.request_id)
            if request is None:
                return Failure(NotFoundError("SynthesisRequest", str(input.request_id)))
            require_same_workspace(auth, request.workspace_id)
            request.fail(reason=input.reason)
            await self._repo.save(request)
            events = await self._uow.commit()
            await self._dispatcher.dispatch_all(events)
            return Success(request)


class CancelSynthesisRequest:
    def __init__(
        self,
        uow: UnitOfWork,
        repo: SynthesisRequestRepository,
        dispatcher: EventDispatcherProtocol,
    ) -> None:
        self._uow = uow
        self._repo = repo
        self._dispatcher = dispatcher

    async def __call__(
        self, input: CancelSynthesisRequestCommand, auth: AuthContext | None = None
    ) -> Result[SynthesisRequest, DomainError]:
        require_editor(auth)
        async with self._uow:
            request = await self._repo.find_by_id(input.request_id)
            if request is None:
                return Failure(NotFoundError("SynthesisRequest", str(input.request_id)))
            require_same_workspace(auth, request.workspace_id)
            request.cancel()
            await self._repo.save(request)
            events = await self._uow.commit()
            await self._dispatcher.dispatch_all(events)
            return Success(request)


class GetSynthesisRequest:
    def __init__(self, uow: UnitOfWork, repo: SynthesisRequestRepository) -> None:
        self._uow = uow
        self._repo = repo

    async def __call__(
        self, input: GetSynthesisRequestQuery, auth: AuthContext | None = None
    ) -> Result[SynthesisRequest, DomainError]:
        async with self._uow:
            request = await self._repo.find_by_id(input.request_id)
            if request is None:
                return Failure(NotFoundError("SynthesisRequest", str(input.request_id)))
            require_same_workspace(auth, request.workspace_id)
            return Success(request)


class ListSynthesisRequests:
    def __init__(self, uow: UnitOfWork, repo: SynthesisRequestRepository) -> None:
        self._uow = uow
        self._repo = repo

    async def __call__(
        self, input: ListSynthesisRequestsQuery, auth: AuthContext | None = None
    ) -> Result[list[SynthesisRequest], DomainError]:
        async with self._uow:
            if input.molecule_id is not None:
                requests = await self._repo.find_by_molecule(
                    input.workspace_id, input.molecule_id
                )
            else:
                requests = await self._repo.find_by_workspace(
                    input.workspace_id, status=input.status
                )
            return Success(requests)
