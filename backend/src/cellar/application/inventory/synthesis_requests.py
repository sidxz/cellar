"""SynthesisRequest use cases — 10-state lifecycle management for compound synthesis requests."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Failure, Result, Success

from cellar.application.auth import (
    AuthContext,
    require_editor,
    require_same_workspace,
    require_workspace_role,
)
from cellar.application.shared.command import Command
from cellar.application.shared.event_dispatcher import EventDispatcherProtocol
from cellar.application.shared.query import Query
from cellar.application.shared.sentinel import UNSET
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.inventory.enums import (
    FeasibilityStatus,
    RequestPriority,
    SynthesisRequestStatus,
)
from cellar.domain.inventory.repository import BatchRepository, SynthesisRequestRepository
from cellar.domain.inventory.synthesis_request import SynthesisRequest
from cellar.domain.shared.enums import AmountUnit, AssignmentType
from cellar.domain.shared.errors import DomainError, NotFoundError, ValidationError
from cellar.domain.shared.value_objects import Amount, SynthesisAssignment

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
    workspace_id: uuid.UUID
    request_id: uuid.UUID


@dataclass(frozen=True, kw_only=True)
class ApproveSynthesisRequestCommand(Command):
    workspace_id: uuid.UUID
    request_id: uuid.UUID
    approved_by: uuid.UUID


@dataclass(frozen=True, kw_only=True)
class RejectSynthesisRequestCommand(Command):
    workspace_id: uuid.UUID
    request_id: uuid.UUID
    reason: str
    rejected_by: uuid.UUID


@dataclass(frozen=True, kw_only=True)
class AssignSynthesisRequestCommand(Command):
    workspace_id: uuid.UUID
    request_id: uuid.UUID
    assignment_type: str
    assigned_to: uuid.UUID | None = None
    assigned_org_id: uuid.UUID | None = None


@dataclass(frozen=True, kw_only=True)
class StartSynthesisCommand(Command):
    workspace_id: uuid.UUID
    request_id: uuid.UUID
    proposed_route_id: uuid.UUID | None = None


@dataclass(frozen=True, kw_only=True)
class FlagInfeasibleCommand(Command):
    workspace_id: uuid.UUID
    request_id: uuid.UUID
    feasibility_status: str
    feasibility_notes: str | None = None


@dataclass(frozen=True, kw_only=True)
class CompleteSynthesisCommand(Command):
    workspace_id: uuid.UUID
    request_id: uuid.UUID
    actual_cost_value: float | None = None
    actual_cost_unit: str | None = None


@dataclass(frozen=True, kw_only=True)
class FulfillSynthesisRequestCommand(Command):
    workspace_id: uuid.UUID
    request_id: uuid.UUID
    batch_id: uuid.UUID


@dataclass(frozen=True, kw_only=True)
class FailSynthesisCommand(Command):
    workspace_id: uuid.UUID
    request_id: uuid.UUID
    reason: str


@dataclass(frozen=True, kw_only=True)
class CancelSynthesisRequestCommand(Command):
    workspace_id: uuid.UUID
    request_id: uuid.UUID


@dataclass(frozen=True, kw_only=True)
class UpdateSynthesisRequestCommand(Command):
    workspace_id: uuid.UUID
    request_id: uuid.UUID
    purpose: str | object = UNSET
    priority: str | object = UNSET
    amount_value: float | object = UNSET
    amount_unit: str | object = UNSET
    target_purity: float | object | None = UNSET


@dataclass(frozen=True, kw_only=True)
class DeleteSynthesisRequestCommand(Command):
    workspace_id: uuid.UUID
    request_id: uuid.UUID


# ---------------------------------------------------------------------------
# Queries
# ---------------------------------------------------------------------------


@dataclass(frozen=True, kw_only=True)
class GetSynthesisRequestQuery(Query):
    workspace_id: uuid.UUID
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
        require_same_workspace(auth, input.workspace_id)
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
        require_same_workspace(auth, input.workspace_id)
        async with self._uow:
            request = await self._repo.find_by_id_in_workspace(
                input.workspace_id, input.request_id
            )
            if request is None:
                return Failure(NotFoundError("SynthesisRequest", str(input.request_id)))
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
        require_same_workspace(auth, input.workspace_id)
        async with self._uow:
            request = await self._repo.find_by_id_in_workspace(
                input.workspace_id, input.request_id
            )
            if request is None:
                return Failure(NotFoundError("SynthesisRequest", str(input.request_id)))
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
        require_same_workspace(auth, input.workspace_id)
        async with self._uow:
            request = await self._repo.find_by_id_in_workspace(
                input.workspace_id, input.request_id
            )
            if request is None:
                return Failure(NotFoundError("SynthesisRequest", str(input.request_id)))
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
        require_same_workspace(auth, input.workspace_id)
        async with self._uow:
            request = await self._repo.find_by_id_in_workspace(
                input.workspace_id, input.request_id
            )
            if request is None:
                return Failure(NotFoundError("SynthesisRequest", str(input.request_id)))
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
        require_same_workspace(auth, input.workspace_id)
        async with self._uow:
            request = await self._repo.find_by_id_in_workspace(
                input.workspace_id, input.request_id
            )
            if request is None:
                return Failure(NotFoundError("SynthesisRequest", str(input.request_id)))
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
        require_same_workspace(auth, input.workspace_id)
        async with self._uow:
            request = await self._repo.find_by_id_in_workspace(
                input.workspace_id, input.request_id
            )
            if request is None:
                return Failure(NotFoundError("SynthesisRequest", str(input.request_id)))
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
        require_same_workspace(auth, input.workspace_id)
        async with self._uow:
            request = await self._repo.find_by_id_in_workspace(
                input.workspace_id, input.request_id
            )
            if request is None:
                return Failure(NotFoundError("SynthesisRequest", str(input.request_id)))
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
        batch_repo: BatchRepository | None = None,
    ) -> None:
        self._uow = uow
        self._repo = repo
        self._dispatcher = dispatcher
        self._batch_repo = batch_repo

    async def __call__(
        self, input: FulfillSynthesisRequestCommand, auth: AuthContext | None = None
    ) -> Result[SynthesisRequest, DomainError]:
        require_editor(auth)
        require_same_workspace(auth, input.workspace_id)
        async with self._uow:
            request = await self._repo.find_by_id_in_workspace(
                input.workspace_id, input.request_id
            )
            if request is None:
                return Failure(NotFoundError("SynthesisRequest", str(input.request_id)))

            # Verify batch belongs to this workspace
            if self._batch_repo is not None:
                batch = await self._batch_repo.find_by_id_in_workspace(
                    input.workspace_id, input.batch_id
                )
                if batch is None:
                    return Failure(NotFoundError("Batch", str(input.batch_id)))

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
        require_same_workspace(auth, input.workspace_id)
        async with self._uow:
            request = await self._repo.find_by_id_in_workspace(
                input.workspace_id, input.request_id
            )
            if request is None:
                return Failure(NotFoundError("SynthesisRequest", str(input.request_id)))
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
        require_same_workspace(auth, input.workspace_id)
        async with self._uow:
            request = await self._repo.find_by_id_in_workspace(
                input.workspace_id, input.request_id
            )
            if request is None:
                return Failure(NotFoundError("SynthesisRequest", str(input.request_id)))
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
        require_workspace_role(auth, "viewer")
        require_same_workspace(auth, input.workspace_id)
        async with self._uow:
            request = await self._repo.find_by_id_in_workspace(
                input.workspace_id, input.request_id
            )
            if request is None:
                return Failure(NotFoundError("SynthesisRequest", str(input.request_id)))
            return Success(request)


class ListSynthesisRequests:
    def __init__(self, uow: UnitOfWork, repo: SynthesisRequestRepository) -> None:
        self._uow = uow
        self._repo = repo

    async def __call__(
        self, input: ListSynthesisRequestsQuery, auth: AuthContext | None = None
    ) -> Result[list[SynthesisRequest], DomainError]:
        require_workspace_role(auth, "viewer")
        require_same_workspace(auth, input.workspace_id)
        async with self._uow:
            if input.molecule_id is not None:
                requests = await self._repo.find_by_molecule(input.workspace_id, input.molecule_id)
            else:
                requests = await self._repo.find_by_workspace(
                    input.workspace_id, status=input.status
                )
            return Success(requests)


class UpdateSynthesisRequest:
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
        self, input: UpdateSynthesisRequestCommand, auth: AuthContext | None = None
    ) -> Result[SynthesisRequest, DomainError]:
        require_editor(auth)
        require_same_workspace(auth, input.workspace_id)
        async with self._uow:
            request = await self._repo.find_by_id_in_workspace(
                input.workspace_id, input.request_id
            )
            if request is None:
                return Failure(NotFoundError("SynthesisRequest", str(input.request_id)))

            try:
                new_amount = ...
                if input.amount_value is not UNSET or input.amount_unit is not UNSET:
                    new_value = (
                        input.amount_value
                        if input.amount_value is not UNSET
                        else request.requested_amount.value
                    )
                    new_unit = (
                        input.amount_unit
                        if input.amount_unit is not UNSET
                        else request.requested_amount.unit.value
                    )
                    new_amount = Amount(value=new_value, unit=AmountUnit(new_unit))

                request.update_details(
                    purpose=input.purpose if input.purpose is not UNSET else ...,
                    priority=RequestPriority(input.priority)
                    if input.priority is not UNSET
                    else ...,
                    target_purity=input.target_purity if input.target_purity is not UNSET else ...,
                    requested_amount=new_amount,
                )
            except ValidationError as exc:
                return Failure(exc)

            await self._repo.save(request)
            events = await self._uow.commit()

        await self._dispatcher.dispatch_all(events)
        return Success(request)


class DeleteSynthesisRequest:
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
        self, input: DeleteSynthesisRequestCommand, auth: AuthContext | None = None
    ) -> Result[None, DomainError]:
        require_editor(auth)
        require_same_workspace(auth, input.workspace_id)
        async with self._uow:
            request = await self._repo.find_by_id_in_workspace(
                input.workspace_id, input.request_id
            )
            if request is None:
                return Failure(NotFoundError("SynthesisRequest", str(input.request_id)))

            if request.status != SynthesisRequestStatus.DRAFT:
                return Failure(ValidationError("Can only delete draft synthesis requests"))

            await self._repo.delete(request.workspace_id, request.id)
            events = await self._uow.commit()

        await self._dispatcher.dispatch_all(events)
        return Success(None)
