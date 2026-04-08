"""Unit tests for SynthesisRequest use cases."""

from __future__ import annotations

import uuid
from types import TracebackType
from typing import Self

import pytest
from returns.result import Failure, Success

from chem_vault.application.inventory.synthesis_requests import (
    ApproveSynthesisRequest,
    ApproveSynthesisRequestCommand,
    AssignSynthesisRequest,
    AssignSynthesisRequestCommand,
    CancelSynthesisRequest,
    CancelSynthesisRequestCommand,
    CompleteSynthesis,
    CompleteSynthesisCommand,
    CreateSynthesisRequest,
    CreateSynthesisRequestCommand,
    FailSynthesis,
    FailSynthesisCommand,
    FlagInfeasible,
    FlagInfeasibleCommand,
    FulfillSynthesisRequest,
    FulfillSynthesisRequestCommand,
    GetSynthesisRequest,
    GetSynthesisRequestQuery,
    ListSynthesisRequests,
    ListSynthesisRequestsQuery,
    RejectSynthesisRequest,
    RejectSynthesisRequestCommand,
    StartSynthesis,
    StartSynthesisCommand,
    SubmitSynthesisRequest,
    SubmitSynthesisRequestCommand,
)
from chem_vault.domain.inventory.enums import SynthesisRequestStatus
from chem_vault.domain.inventory.synthesis_request import SynthesisRequest
from chem_vault.domain.shared.enums import AmountUnit, AssignmentType
from chem_vault.domain.shared.errors import NotFoundError, ValidationError
from chem_vault.domain.shared.events import DomainEvent
from chem_vault.domain.shared.value_objects import Amount, SynthesisAssignment
from tests.fakes.fake_auth import FakeAuth


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------

WS_ID = uuid.uuid4()
OTHER_WS_ID = uuid.uuid4()


class FakeSynthesisRequestRepo:
    def __init__(self, items: list[SynthesisRequest] | None = None) -> None:
        self._store: dict[uuid.UUID, SynthesisRequest] = {
            item.id: item for item in (items or [])
        }

    async def find_by_id(self, id: uuid.UUID) -> SynthesisRequest | None:
        return self._store.get(id)

    async def find_by_id_in_workspace(
        self, workspace_id: uuid.UUID, id: uuid.UUID
    ) -> SynthesisRequest | None:
        item = self._store.get(id)
        if item is not None and item.workspace_id == workspace_id:
            return item
        return None

    async def find_by_workspace(
        self, workspace_id: uuid.UUID, *, status: str | None = None
    ) -> list[SynthesisRequest]:
        results = [r for r in self._store.values() if r.workspace_id == workspace_id]
        if status:
            results = [r for r in results if r.status.value == status]
        return results

    async def find_by_molecule(
        self, workspace_id: uuid.UUID, molecule_id: uuid.UUID
    ) -> list[SynthesisRequest]:
        return [
            r
            for r in self._store.values()
            if r.workspace_id == workspace_id and r.molecule_id == molecule_id
        ]

    async def save(self, aggregate: SynthesisRequest) -> None:
        self._store[aggregate.id] = aggregate


class FakeUoW:
    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        pass

    async def commit(self) -> list[DomainEvent]:
        return []


class FakeDispatcher:
    def __init__(self) -> None:
        self.dispatched: list[DomainEvent] = []

    async def dispatch_all(self, events: list[DomainEvent]) -> None:
        self.dispatched.extend(events)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_request(
    workspace_id: uuid.UUID = WS_ID,
    status: str = "draft",
    molecule_id: uuid.UUID | None = None,
) -> SynthesisRequest:
    """Build a SynthesisRequest in a given status via factory + manual transitions."""
    sr = SynthesisRequest.create(
        workspace_id=workspace_id,
        requester_id=uuid.uuid4(),
        molecule_id=molecule_id or uuid.uuid4(),
        requested_amount=Amount(value=10.0, unit=AmountUnit.MG),
        purpose="SAR study",
    )
    sr.clear_events()

    if status == "draft":
        return sr

    sr.submit()
    sr.clear_events()
    if status == "submitted":
        return sr

    sr.approve(approved_by=uuid.uuid4())
    sr.clear_events()
    if status == "approved":
        return sr

    sr.assign(SynthesisAssignment(assignment_type=AssignmentType.INTERNAL, assigned_to=uuid.uuid4()))
    sr.clear_events()
    if status == "assigned":
        return sr

    sr.start()
    sr.clear_events()
    if status == "in_progress":
        return sr

    sr.complete_synthesis()
    sr.clear_events()
    if status == "synthesis_complete":
        return sr

    sr.fulfill(batch_id=uuid.uuid4())
    sr.clear_events()
    if status == "fulfilled":
        return sr

    return sr


def _make_auth(workspace_id: uuid.UUID = WS_ID, role: str = "editor") -> FakeAuth:
    return FakeAuth(workspace_id=workspace_id, role=role)


# ---------------------------------------------------------------------------
# CreateSynthesisRequest
# ---------------------------------------------------------------------------


class TestCreateSynthesisRequest:
    @pytest.mark.asyncio
    async def test_creates_in_draft_status(self) -> None:
        repo = FakeSynthesisRequestRepo()
        uc = CreateSynthesisRequest(FakeUoW(), repo, FakeDispatcher())
        auth = _make_auth()

        cmd = CreateSynthesisRequestCommand(
            workspace_id=WS_ID,
            requester_id=auth.user_id,
            molecule_id=uuid.uuid4(),
            amount_value=5.0,
            amount_unit="mg",
            purpose="Lead optimization",
        )
        result = await uc(cmd, auth)

        assert isinstance(result, Success)
        req = result.unwrap()
        assert req.status == SynthesisRequestStatus.DRAFT
        assert req.workspace_id == WS_ID
        assert req.purpose == "Lead optimization"
        assert req.requested_amount.value == 5.0
        assert req.requested_amount.unit == AmountUnit.MG

    @pytest.mark.asyncio
    async def test_persists_to_repo(self) -> None:
        repo = FakeSynthesisRequestRepo()
        uc = CreateSynthesisRequest(FakeUoW(), repo, FakeDispatcher())
        auth = _make_auth()

        cmd = CreateSynthesisRequestCommand(
            workspace_id=WS_ID,
            requester_id=auth.user_id,
            molecule_id=uuid.uuid4(),
            amount_value=10.0,
            amount_unit="mg",
            purpose="Check persistence",
        )
        result = await uc(cmd, auth)
        req = result.unwrap()

        stored = await repo.find_by_id(req.id)
        assert stored is not None
        assert stored.id == req.id

    @pytest.mark.asyncio
    async def test_creates_with_optional_fields(self) -> None:
        repo = FakeSynthesisRequestRepo()
        uc = CreateSynthesisRequest(FakeUoW(), repo, FakeDispatcher())
        auth = _make_auth()
        project_id = uuid.uuid4()
        parent_id = uuid.uuid4()

        cmd = CreateSynthesisRequestCommand(
            workspace_id=WS_ID,
            requester_id=auth.user_id,
            molecule_id=uuid.uuid4(),
            amount_value=25.0,
            amount_unit="g",
            purpose="Scale-up",
            priority="urgent",
            target_purity=95.0,
            project_id=project_id,
            parent_request_id=parent_id,
        )
        result = await uc(cmd, auth)

        assert isinstance(result, Success)
        req = result.unwrap()
        assert req.target_purity == 95.0
        assert req.project_id == project_id
        assert req.parent_request_id == parent_id

    @pytest.mark.asyncio
    async def test_viewer_cannot_create(self) -> None:
        repo = FakeSynthesisRequestRepo()
        uc = CreateSynthesisRequest(FakeUoW(), repo, FakeDispatcher())
        auth = FakeAuth(workspace_id=WS_ID, role="viewer")

        cmd = CreateSynthesisRequestCommand(
            workspace_id=WS_ID,
            requester_id=auth.user_id,
            molecule_id=uuid.uuid4(),
            amount_value=5.0,
            amount_unit="mg",
            purpose="Should fail",
        )
        with pytest.raises(Exception):
            await uc(cmd, auth)


# ---------------------------------------------------------------------------
# SubmitSynthesisRequest
# ---------------------------------------------------------------------------


class TestSubmitSynthesisRequest:
    @pytest.mark.asyncio
    async def test_transitions_draft_to_submitted(self) -> None:
        req = _make_request(status="draft")
        repo = FakeSynthesisRequestRepo([req])
        uc = SubmitSynthesisRequest(FakeUoW(), repo, FakeDispatcher())
        auth = _make_auth()

        result = await uc(SubmitSynthesisRequestCommand(workspace_id=WS_ID, request_id=req.id), auth)

        assert isinstance(result, Success)
        assert result.unwrap().status == SynthesisRequestStatus.SUBMITTED

    @pytest.mark.asyncio
    async def test_returns_failure_for_not_found(self) -> None:
        repo = FakeSynthesisRequestRepo()
        uc = SubmitSynthesisRequest(FakeUoW(), repo, FakeDispatcher())
        auth = _make_auth()

        result = await uc(SubmitSynthesisRequestCommand(workspace_id=WS_ID, request_id=uuid.uuid4()), auth)

        assert isinstance(result, Failure)
        assert isinstance(result.failure(), NotFoundError)

    @pytest.mark.asyncio
    async def test_cannot_submit_already_submitted(self) -> None:
        req = _make_request(status="submitted")
        repo = FakeSynthesisRequestRepo([req])
        uc = SubmitSynthesisRequest(FakeUoW(), repo, FakeDispatcher())
        auth = _make_auth()

        with pytest.raises(ValidationError):
            await uc(SubmitSynthesisRequestCommand(workspace_id=WS_ID, request_id=req.id), auth)


# ---------------------------------------------------------------------------
# ApproveSynthesisRequest
# ---------------------------------------------------------------------------


class TestApproveSynthesisRequest:
    @pytest.mark.asyncio
    async def test_transitions_to_approved(self) -> None:
        req = _make_request(status="submitted")
        repo = FakeSynthesisRequestRepo([req])
        uc = ApproveSynthesisRequest(FakeUoW(), repo, FakeDispatcher())
        auth = _make_auth()

        result = await uc(
            ApproveSynthesisRequestCommand(workspace_id=WS_ID, request_id=req.id, approved_by=auth.user_id),
            auth,
        )

        assert isinstance(result, Success)
        approved = result.unwrap()
        assert approved.status == SynthesisRequestStatus.APPROVED
        assert approved.approved_by == auth.user_id

    @pytest.mark.asyncio
    async def test_returns_failure_for_not_found(self) -> None:
        repo = FakeSynthesisRequestRepo()
        uc = ApproveSynthesisRequest(FakeUoW(), repo, FakeDispatcher())
        auth = _make_auth()

        result = await uc(
            ApproveSynthesisRequestCommand(workspace_id=WS_ID, request_id=uuid.uuid4(), approved_by=auth.user_id),
            auth,
        )

        assert isinstance(result, Failure)
        assert isinstance(result.failure(), NotFoundError)

    @pytest.mark.asyncio
    async def test_cannot_approve_already_approved(self) -> None:
        req = _make_request(status="approved")
        repo = FakeSynthesisRequestRepo([req])
        uc = ApproveSynthesisRequest(FakeUoW(), repo, FakeDispatcher())
        auth = _make_auth()

        with pytest.raises(ValidationError):
            await uc(
                ApproveSynthesisRequestCommand(workspace_id=WS_ID, request_id=req.id, approved_by=auth.user_id),
                auth,
            )


# ---------------------------------------------------------------------------
# RejectSynthesisRequest
# ---------------------------------------------------------------------------


class TestRejectSynthesisRequest:
    @pytest.mark.asyncio
    async def test_transitions_to_rejected_with_reason(self) -> None:
        req = _make_request(status="submitted")
        repo = FakeSynthesisRequestRepo([req])
        uc = RejectSynthesisRequest(FakeUoW(), repo, FakeDispatcher())
        auth = _make_auth()

        result = await uc(
            RejectSynthesisRequestCommand(
                workspace_id=WS_ID, request_id=req.id, reason="Not feasible", rejected_by=auth.user_id
            ),
            auth,
        )

        assert isinstance(result, Success)
        rejected = result.unwrap()
        assert rejected.status == SynthesisRequestStatus.REJECTED
        assert rejected.rejection_reason == "Not feasible"

    @pytest.mark.asyncio
    async def test_returns_failure_for_not_found(self) -> None:
        repo = FakeSynthesisRequestRepo()
        uc = RejectSynthesisRequest(FakeUoW(), repo, FakeDispatcher())
        auth = _make_auth()

        result = await uc(
            RejectSynthesisRequestCommand(
                workspace_id=WS_ID, request_id=uuid.uuid4(), reason="No stock", rejected_by=auth.user_id
            ),
            auth,
        )

        assert isinstance(result, Failure)
        assert isinstance(result.failure(), NotFoundError)

    @pytest.mark.asyncio
    async def test_empty_reason_raises_validation_error(self) -> None:
        req = _make_request(status="submitted")
        repo = FakeSynthesisRequestRepo([req])
        uc = RejectSynthesisRequest(FakeUoW(), repo, FakeDispatcher())
        auth = _make_auth()

        with pytest.raises(ValidationError):
            await uc(
                RejectSynthesisRequestCommand(
                    workspace_id=WS_ID, request_id=req.id, reason="   ", rejected_by=auth.user_id
                ),
                auth,
            )


# ---------------------------------------------------------------------------
# AssignSynthesisRequest
# ---------------------------------------------------------------------------


class TestAssignSynthesisRequest:
    @pytest.mark.asyncio
    async def test_assigns_internal(self) -> None:
        req = _make_request(status="approved")
        repo = FakeSynthesisRequestRepo([req])
        uc = AssignSynthesisRequest(FakeUoW(), repo, FakeDispatcher())
        auth = _make_auth()
        assignee = uuid.uuid4()

        result = await uc(
            AssignSynthesisRequestCommand(
                workspace_id=WS_ID,
                request_id=req.id,
                assignment_type="internal",
                assigned_to=assignee,
            ),
            auth,
        )

        assert isinstance(result, Success)
        assigned = result.unwrap()
        assert assigned.status == SynthesisRequestStatus.ASSIGNED
        assert assigned.assignment is not None
        assert assigned.assignment.assignment_type == AssignmentType.INTERNAL
        assert assigned.assignment.assigned_to == assignee

    @pytest.mark.asyncio
    async def test_assigns_cro(self) -> None:
        req = _make_request(status="approved")
        repo = FakeSynthesisRequestRepo([req])
        uc = AssignSynthesisRequest(FakeUoW(), repo, FakeDispatcher())
        auth = _make_auth()
        org_id = uuid.uuid4()

        result = await uc(
            AssignSynthesisRequestCommand(
                workspace_id=WS_ID,
                request_id=req.id,
                assignment_type="cro",
                assigned_org_id=org_id,
            ),
            auth,
        )

        assert isinstance(result, Success)
        assigned = result.unwrap()
        assert assigned.status == SynthesisRequestStatus.ASSIGNED
        assert assigned.assignment is not None
        assert assigned.assignment.assignment_type == AssignmentType.CRO
        assert assigned.assignment.assigned_org_id == org_id

    @pytest.mark.asyncio
    async def test_returns_failure_for_not_found(self) -> None:
        repo = FakeSynthesisRequestRepo()
        uc = AssignSynthesisRequest(FakeUoW(), repo, FakeDispatcher())
        auth = _make_auth()

        result = await uc(
            AssignSynthesisRequestCommand(
                workspace_id=WS_ID,
                request_id=uuid.uuid4(),
                assignment_type="internal",
                assigned_to=uuid.uuid4(),
            ),
            auth,
        )

        assert isinstance(result, Failure)
        assert isinstance(result.failure(), NotFoundError)

    @pytest.mark.asyncio
    async def test_cannot_assign_from_draft(self) -> None:
        req = _make_request(status="draft")
        repo = FakeSynthesisRequestRepo([req])
        uc = AssignSynthesisRequest(FakeUoW(), repo, FakeDispatcher())
        auth = _make_auth()

        with pytest.raises(ValidationError):
            await uc(
                AssignSynthesisRequestCommand(
                    workspace_id=WS_ID,
                    request_id=req.id,
                    assignment_type="internal",
                    assigned_to=uuid.uuid4(),
                ),
                auth,
            )


# ---------------------------------------------------------------------------
# StartSynthesis
# ---------------------------------------------------------------------------


class TestStartSynthesis:
    @pytest.mark.asyncio
    async def test_transitions_to_in_progress(self) -> None:
        req = _make_request(status="assigned")
        repo = FakeSynthesisRequestRepo([req])
        uc = StartSynthesis(FakeUoW(), repo, FakeDispatcher())
        auth = _make_auth()

        result = await uc(StartSynthesisCommand(workspace_id=WS_ID, request_id=req.id), auth)

        assert isinstance(result, Success)
        assert result.unwrap().status == SynthesisRequestStatus.IN_PROGRESS

    @pytest.mark.asyncio
    async def test_with_proposed_route(self) -> None:
        req = _make_request(status="assigned")
        repo = FakeSynthesisRequestRepo([req])
        uc = StartSynthesis(FakeUoW(), repo, FakeDispatcher())
        auth = _make_auth()
        route_id = uuid.uuid4()

        result = await uc(
            StartSynthesisCommand(workspace_id=WS_ID, request_id=req.id, proposed_route_id=route_id), auth
        )

        assert isinstance(result, Success)
        assert result.unwrap().proposed_route_id == route_id

    @pytest.mark.asyncio
    async def test_returns_failure_for_not_found(self) -> None:
        repo = FakeSynthesisRequestRepo()
        uc = StartSynthesis(FakeUoW(), repo, FakeDispatcher())
        auth = _make_auth()

        result = await uc(StartSynthesisCommand(workspace_id=WS_ID, request_id=uuid.uuid4()), auth)

        assert isinstance(result, Failure)
        assert isinstance(result.failure(), NotFoundError)

    @pytest.mark.asyncio
    async def test_cannot_start_from_approved(self) -> None:
        req = _make_request(status="approved")
        repo = FakeSynthesisRequestRepo([req])
        uc = StartSynthesis(FakeUoW(), repo, FakeDispatcher())
        auth = _make_auth()

        with pytest.raises(ValidationError):
            await uc(StartSynthesisCommand(workspace_id=WS_ID, request_id=req.id), auth)


# ---------------------------------------------------------------------------
# FlagInfeasible
# ---------------------------------------------------------------------------


class TestFlagInfeasible:
    @pytest.mark.asyncio
    async def test_returns_to_approved_and_clears_assignment(self) -> None:
        req = _make_request(status="assigned")
        repo = FakeSynthesisRequestRepo([req])
        uc = FlagInfeasible(FakeUoW(), repo, FakeDispatcher())
        auth = _make_auth()

        result = await uc(
            FlagInfeasibleCommand(
                workspace_id=WS_ID,
                request_id=req.id,
                feasibility_status="infeasible",
                feasibility_notes="Route too complex",
            ),
            auth,
        )

        assert isinstance(result, Success)
        flagged = result.unwrap()
        assert flagged.status == SynthesisRequestStatus.APPROVED
        assert flagged.assignment is None
        assert flagged.feasibility_notes == "Route too complex"

    @pytest.mark.asyncio
    async def test_returns_failure_for_not_found(self) -> None:
        repo = FakeSynthesisRequestRepo()
        uc = FlagInfeasible(FakeUoW(), repo, FakeDispatcher())
        auth = _make_auth()

        result = await uc(
            FlagInfeasibleCommand(
                workspace_id=WS_ID, request_id=uuid.uuid4(), feasibility_status="infeasible"
            ),
            auth,
        )

        assert isinstance(result, Failure)
        assert isinstance(result.failure(), NotFoundError)


# ---------------------------------------------------------------------------
# CompleteSynthesis
# ---------------------------------------------------------------------------


class TestCompleteSynthesis:
    @pytest.mark.asyncio
    async def test_transitions_to_synthesis_complete(self) -> None:
        req = _make_request(status="in_progress")
        repo = FakeSynthesisRequestRepo([req])
        uc = CompleteSynthesis(FakeUoW(), repo, FakeDispatcher())
        auth = _make_auth()

        result = await uc(CompleteSynthesisCommand(workspace_id=WS_ID, request_id=req.id), auth)

        assert isinstance(result, Success)
        assert result.unwrap().status == SynthesisRequestStatus.SYNTHESIS_COMPLETE

    @pytest.mark.asyncio
    async def test_with_actual_cost(self) -> None:
        req = _make_request(status="in_progress")
        repo = FakeSynthesisRequestRepo([req])
        uc = CompleteSynthesis(FakeUoW(), repo, FakeDispatcher())
        auth = _make_auth()

        result = await uc(
            CompleteSynthesisCommand(
                workspace_id=WS_ID, request_id=req.id, actual_cost_value=150.0, actual_cost_unit="mg"
            ),
            auth,
        )

        assert isinstance(result, Success)
        completed = result.unwrap()
        assert completed.actual_cost is not None
        assert completed.actual_cost.value == 150.0
        assert completed.actual_cost.unit == AmountUnit.MG

    @pytest.mark.asyncio
    async def test_returns_failure_for_not_found(self) -> None:
        repo = FakeSynthesisRequestRepo()
        uc = CompleteSynthesis(FakeUoW(), repo, FakeDispatcher())
        auth = _make_auth()

        result = await uc(CompleteSynthesisCommand(workspace_id=WS_ID, request_id=uuid.uuid4()), auth)

        assert isinstance(result, Failure)
        assert isinstance(result.failure(), NotFoundError)

    @pytest.mark.asyncio
    async def test_cannot_complete_from_assigned(self) -> None:
        req = _make_request(status="assigned")
        repo = FakeSynthesisRequestRepo([req])
        uc = CompleteSynthesis(FakeUoW(), repo, FakeDispatcher())
        auth = _make_auth()

        with pytest.raises(ValidationError):
            await uc(CompleteSynthesisCommand(workspace_id=WS_ID, request_id=req.id), auth)


# ---------------------------------------------------------------------------
# FulfillSynthesisRequest
# ---------------------------------------------------------------------------


class TestFulfillSynthesisRequest:
    @pytest.mark.asyncio
    async def test_transitions_to_fulfilled(self) -> None:
        req = _make_request(status="synthesis_complete")
        repo = FakeSynthesisRequestRepo([req])
        uc = FulfillSynthesisRequest(FakeUoW(), repo, FakeDispatcher())
        auth = _make_auth()
        batch_id = uuid.uuid4()

        result = await uc(
            FulfillSynthesisRequestCommand(workspace_id=WS_ID, request_id=req.id, batch_id=batch_id), auth
        )

        assert isinstance(result, Success)
        fulfilled = result.unwrap()
        assert fulfilled.status == SynthesisRequestStatus.FULFILLED
        assert fulfilled.fulfilled_batch_id == batch_id

    @pytest.mark.asyncio
    async def test_returns_failure_for_not_found(self) -> None:
        repo = FakeSynthesisRequestRepo()
        uc = FulfillSynthesisRequest(FakeUoW(), repo, FakeDispatcher())
        auth = _make_auth()

        result = await uc(
            FulfillSynthesisRequestCommand(workspace_id=WS_ID, request_id=uuid.uuid4(), batch_id=uuid.uuid4()),
            auth,
        )

        assert isinstance(result, Failure)
        assert isinstance(result.failure(), NotFoundError)

    @pytest.mark.asyncio
    async def test_cannot_fulfill_from_in_progress(self) -> None:
        req = _make_request(status="in_progress")
        repo = FakeSynthesisRequestRepo([req])
        uc = FulfillSynthesisRequest(FakeUoW(), repo, FakeDispatcher())
        auth = _make_auth()

        with pytest.raises(ValidationError):
            await uc(
                FulfillSynthesisRequestCommand(workspace_id=WS_ID, request_id=req.id, batch_id=uuid.uuid4()),
                auth,
            )


# ---------------------------------------------------------------------------
# FailSynthesis
# ---------------------------------------------------------------------------


class TestFailSynthesis:
    @pytest.mark.asyncio
    async def test_transitions_to_failed(self) -> None:
        req = _make_request(status="in_progress")
        repo = FakeSynthesisRequestRepo([req])
        uc = FailSynthesis(FakeUoW(), repo, FakeDispatcher())
        auth = _make_auth()

        result = await uc(
            FailSynthesisCommand(workspace_id=WS_ID, request_id=req.id, reason="Yield too low"), auth
        )

        assert isinstance(result, Success)
        failed = result.unwrap()
        assert failed.status == SynthesisRequestStatus.FAILED
        assert failed.failure_reason == "Yield too low"

    @pytest.mark.asyncio
    async def test_returns_failure_for_not_found(self) -> None:
        repo = FakeSynthesisRequestRepo()
        uc = FailSynthesis(FakeUoW(), repo, FakeDispatcher())
        auth = _make_auth()

        result = await uc(
            FailSynthesisCommand(workspace_id=WS_ID, request_id=uuid.uuid4(), reason="No reason"), auth
        )

        assert isinstance(result, Failure)
        assert isinstance(result.failure(), NotFoundError)

    @pytest.mark.asyncio
    async def test_empty_reason_raises_validation_error(self) -> None:
        req = _make_request(status="in_progress")
        repo = FakeSynthesisRequestRepo([req])
        uc = FailSynthesis(FakeUoW(), repo, FakeDispatcher())
        auth = _make_auth()

        with pytest.raises(ValidationError):
            await uc(
                FailSynthesisCommand(workspace_id=WS_ID, request_id=req.id, reason="   "), auth
            )


# ---------------------------------------------------------------------------
# CancelSynthesisRequest
# ---------------------------------------------------------------------------


class TestCancelSynthesisRequest:
    @pytest.mark.asyncio
    async def test_cancels_from_submitted(self) -> None:
        req = _make_request(status="submitted")
        repo = FakeSynthesisRequestRepo([req])
        uc = CancelSynthesisRequest(FakeUoW(), repo, FakeDispatcher())
        auth = _make_auth()

        result = await uc(CancelSynthesisRequestCommand(workspace_id=WS_ID, request_id=req.id), auth)

        assert isinstance(result, Success)
        assert result.unwrap().status == SynthesisRequestStatus.CANCELLED

    @pytest.mark.asyncio
    async def test_cancels_from_approved(self) -> None:
        req = _make_request(status="approved")
        repo = FakeSynthesisRequestRepo([req])
        uc = CancelSynthesisRequest(FakeUoW(), repo, FakeDispatcher())
        auth = _make_auth()

        result = await uc(CancelSynthesisRequestCommand(workspace_id=WS_ID, request_id=req.id), auth)

        assert isinstance(result, Success)
        assert result.unwrap().status == SynthesisRequestStatus.CANCELLED

    @pytest.mark.asyncio
    async def test_cancels_from_assigned(self) -> None:
        req = _make_request(status="assigned")
        repo = FakeSynthesisRequestRepo([req])
        uc = CancelSynthesisRequest(FakeUoW(), repo, FakeDispatcher())
        auth = _make_auth()

        result = await uc(CancelSynthesisRequestCommand(workspace_id=WS_ID, request_id=req.id), auth)

        assert isinstance(result, Success)
        assert result.unwrap().status == SynthesisRequestStatus.CANCELLED

    @pytest.mark.asyncio
    async def test_returns_failure_for_not_found(self) -> None:
        repo = FakeSynthesisRequestRepo()
        uc = CancelSynthesisRequest(FakeUoW(), repo, FakeDispatcher())
        auth = _make_auth()

        result = await uc(CancelSynthesisRequestCommand(workspace_id=WS_ID, request_id=uuid.uuid4()), auth)

        assert isinstance(result, Failure)
        assert isinstance(result.failure(), NotFoundError)

    @pytest.mark.asyncio
    async def test_cannot_cancel_fulfilled(self) -> None:
        req = _make_request(status="fulfilled")
        repo = FakeSynthesisRequestRepo([req])
        uc = CancelSynthesisRequest(FakeUoW(), repo, FakeDispatcher())
        auth = _make_auth()

        with pytest.raises(ValidationError):
            await uc(CancelSynthesisRequestCommand(workspace_id=WS_ID, request_id=req.id), auth)

    @pytest.mark.asyncio
    async def test_cannot_cancel_in_progress(self) -> None:
        req = _make_request(status="in_progress")
        repo = FakeSynthesisRequestRepo([req])
        uc = CancelSynthesisRequest(FakeUoW(), repo, FakeDispatcher())
        auth = _make_auth()

        with pytest.raises(ValidationError):
            await uc(CancelSynthesisRequestCommand(workspace_id=WS_ID, request_id=req.id), auth)


# ---------------------------------------------------------------------------
# GetSynthesisRequest
# ---------------------------------------------------------------------------


class TestGetSynthesisRequest:
    @pytest.mark.asyncio
    async def test_returns_found_request(self) -> None:
        req = _make_request()
        repo = FakeSynthesisRequestRepo([req])
        uc = GetSynthesisRequest(FakeUoW(), repo)
        auth = _make_auth()

        result = await uc(GetSynthesisRequestQuery(workspace_id=WS_ID, request_id=req.id), auth)

        assert isinstance(result, Success)
        assert result.unwrap().id == req.id

    @pytest.mark.asyncio
    async def test_returns_failure_when_not_found(self) -> None:
        repo = FakeSynthesisRequestRepo()
        uc = GetSynthesisRequest(FakeUoW(), repo)
        auth = _make_auth()

        result = await uc(GetSynthesisRequestQuery(workspace_id=WS_ID, request_id=uuid.uuid4()), auth)

        assert isinstance(result, Failure)
        assert isinstance(result.failure(), NotFoundError)

    @pytest.mark.asyncio
    async def test_cross_workspace_returns_failure(self) -> None:
        req = _make_request(workspace_id=OTHER_WS_ID)
        repo = FakeSynthesisRequestRepo([req])
        uc = GetSynthesisRequest(FakeUoW(), repo)
        auth = _make_auth(workspace_id=WS_ID)

        result = await uc(GetSynthesisRequestQuery(workspace_id=WS_ID, request_id=req.id), auth)
        assert isinstance(result, Failure)


# ---------------------------------------------------------------------------
# ListSynthesisRequests
# ---------------------------------------------------------------------------


class TestListSynthesisRequests:
    @pytest.mark.asyncio
    async def test_returns_workspace_requests(self) -> None:
        req1 = _make_request(workspace_id=WS_ID)
        req2 = _make_request(workspace_id=WS_ID)
        req_other = _make_request(workspace_id=OTHER_WS_ID)
        repo = FakeSynthesisRequestRepo([req1, req2, req_other])
        uc = ListSynthesisRequests(FakeUoW(), repo)
        auth = _make_auth()

        result = await uc(ListSynthesisRequestsQuery(workspace_id=WS_ID), auth)

        assert isinstance(result, Success)
        ids = {r.id for r in result.unwrap()}
        assert req1.id in ids
        assert req2.id in ids
        assert req_other.id not in ids

    @pytest.mark.asyncio
    async def test_filters_by_status(self) -> None:
        submitted = _make_request(status="submitted")
        approved = _make_request(status="approved")
        repo = FakeSynthesisRequestRepo([submitted, approved])
        uc = ListSynthesisRequests(FakeUoW(), repo)
        auth = _make_auth()

        result = await uc(
            ListSynthesisRequestsQuery(workspace_id=WS_ID, status="submitted"), auth
        )

        assert isinstance(result, Success)
        requests = result.unwrap()
        assert all(r.status == SynthesisRequestStatus.SUBMITTED for r in requests)
        assert approved.id not in {r.id for r in requests}

    @pytest.mark.asyncio
    async def test_filters_by_molecule_id(self) -> None:
        mol_id = uuid.uuid4()
        other_mol_id = uuid.uuid4()
        req1 = _make_request(molecule_id=mol_id)
        req2 = _make_request(molecule_id=other_mol_id)
        repo = FakeSynthesisRequestRepo([req1, req2])
        uc = ListSynthesisRequests(FakeUoW(), repo)
        auth = _make_auth()

        result = await uc(
            ListSynthesisRequestsQuery(workspace_id=WS_ID, molecule_id=mol_id), auth
        )

        assert isinstance(result, Success)
        requests = result.unwrap()
        assert len(requests) == 1
        assert requests[0].molecule_id == mol_id

    @pytest.mark.asyncio
    async def test_empty_workspace_returns_empty_list(self) -> None:
        repo = FakeSynthesisRequestRepo()
        uc = ListSynthesisRequests(FakeUoW(), repo)
        auth = _make_auth()

        result = await uc(ListSynthesisRequestsQuery(workspace_id=WS_ID), auth)

        assert isinstance(result, Success)
        assert result.unwrap() == []
