"""Tests for SynthesisRequest aggregate root — 10-state machine."""

import uuid
from datetime import date

import pytest

from chem_vault.domain.inventory.enums import (
    FeasibilityStatus,
    RequestPriority,
    SynthesisRequestStatus,
)
from chem_vault.domain.inventory.events import (
    SynthesisCompleted,
    SynthesisFailed,
    SynthesisFeasibilityFlagged,
    SynthesisRequestApproved,
    SynthesisRequestAssigned,
    SynthesisRequestCreated,
    SynthesisRequestFulfilled,
    SynthesisRequestRejected,
    SynthesisRequested,
    SynthesisStarted,
)
from chem_vault.domain.inventory.synthesis_request import SynthesisRequest
from chem_vault.domain.shared.enums import AmountUnit, AssignmentType
from chem_vault.domain.shared.errors import ValidationError
from chem_vault.domain.shared.value_objects import Amount, SynthesisAssignment


@pytest.fixture
def ws_id() -> uuid.UUID:
    return uuid.uuid4()


def _make_request(ws_id: uuid.UUID, **overrides) -> SynthesisRequest:
    defaults = dict(
        workspace_id=ws_id,
        requester_id=uuid.uuid4(),
        molecule_id=uuid.uuid4(),
        requested_amount=Amount(value=50.0, unit=AmountUnit.MG),
        purpose="Lead optimization SAR study",
    )
    defaults.update(overrides)
    return SynthesisRequest.create(**defaults)


def _internal_assignment() -> SynthesisAssignment:
    return SynthesisAssignment(
        assignment_type=AssignmentType.INTERNAL,
        assigned_to=uuid.uuid4(),
    )


def _cro_assignment() -> SynthesisAssignment:
    return SynthesisAssignment(
        assignment_type=AssignmentType.CRO,
        assigned_org_id=uuid.uuid4(),
    )


# ---------------------------------------------------------------------------
# Creation
# ---------------------------------------------------------------------------


class TestSynthesisRequestCreation:
    def test_create_basic(self, ws_id):
        req = _make_request(ws_id)
        assert req.status == SynthesisRequestStatus.DRAFT
        assert req.priority == RequestPriority.ROUTINE
        assert req.requested_amount.value == 50.0
        assert req.purpose == "Lead optimization SAR study"
        assert req.is_terminal is False

    def test_create_emits_created_event(self, ws_id):
        """Draft creation emits SynthesisRequestCreated."""
        req = _make_request(ws_id)
        events = req.collect_events()
        assert len(events) == 1
        assert events[0].__class__.__name__ == "SynthesisRequestCreated"
        assert events[0].molecule_id == req.molecule_id
        assert events[0].requested_by == req.requester_id

    def test_create_with_priority(self, ws_id):
        req = _make_request(ws_id, priority=RequestPriority.URGENT)
        assert req.priority == RequestPriority.URGENT

    def test_create_with_purity(self, ws_id):
        req = _make_request(ws_id, target_purity=95.0)
        assert req.target_purity == 95.0

    def test_create_with_project(self, ws_id):
        project_id = uuid.uuid4()
        req = _make_request(ws_id, project_id=project_id)
        assert req.project_id == project_id

    def test_create_with_parent_request(self, ws_id):
        parent_id = uuid.uuid4()
        req = _make_request(ws_id, parent_request_id=parent_id)
        assert req.parent_request_id == parent_id

    def test_create_zero_amount_raises(self, ws_id):
        with pytest.raises(ValidationError, match="positive"):
            _make_request(ws_id, requested_amount=Amount(value=0, unit=AmountUnit.MG))

    def test_create_negative_amount_raises(self, ws_id):
        """Negative amounts are caught by the Amount VO before domain validation."""
        with pytest.raises(Exception, match="must be >= 0"):
            _make_request(ws_id, requested_amount=Amount(value=-1, unit=AmountUnit.MG))

    def test_create_empty_purpose_raises(self, ws_id):
        with pytest.raises(ValidationError, match="Purpose"):
            _make_request(ws_id, purpose="   ")

    def test_create_purity_zero_raises(self, ws_id):
        with pytest.raises(ValidationError, match="purity"):
            _make_request(ws_id, target_purity=0)

    def test_create_purity_negative_raises(self, ws_id):
        with pytest.raises(ValidationError, match="purity"):
            _make_request(ws_id, target_purity=-5)

    def test_create_purity_over_100_raises(self, ws_id):
        with pytest.raises(ValidationError, match="purity"):
            _make_request(ws_id, target_purity=100.1)

    def test_create_purity_exactly_100_ok(self, ws_id):
        req = _make_request(ws_id, target_purity=100.0)
        assert req.target_purity == 100.0


# ---------------------------------------------------------------------------
# Full happy path
# ---------------------------------------------------------------------------


class TestFullLifecycle:
    def test_happy_path_internal(self, ws_id):
        """draft -> submitted -> approved -> assigned -> in_progress -> complete -> fulfilled."""
        req = _make_request(ws_id)
        approver = uuid.uuid4()
        assignment = _internal_assignment()
        route_id = uuid.uuid4()
        batch_id = uuid.uuid4()

        req.submit()
        assert req.status == SynthesisRequestStatus.SUBMITTED

        req.approve(approver)
        assert req.status == SynthesisRequestStatus.APPROVED
        assert req.approved_by == approver
        assert req.approved_at is not None

        req.assign(assignment)
        assert req.status == SynthesisRequestStatus.ASSIGNED
        assert req.assignment == assignment

        req.start(proposed_route_id=route_id)
        assert req.status == SynthesisRequestStatus.IN_PROGRESS
        assert req.proposed_route_id == route_id

        cost = Amount(value=1500.0, unit=AmountUnit.MG)
        req.complete_synthesis(actual_cost=cost)
        assert req.status == SynthesisRequestStatus.SYNTHESIS_COMPLETE
        assert req.actual_cost == cost
        assert req.actual_completion_date is not None

        req.fulfill(batch_id)
        assert req.status == SynthesisRequestStatus.FULFILLED
        assert req.fulfilled_batch_id == batch_id
        assert req.is_terminal is True

    def test_happy_path_cro(self, ws_id):
        """Same lifecycle but with CRO assignment."""
        req = _make_request(ws_id)
        req.submit()
        req.approve(uuid.uuid4())
        req.assign(_cro_assignment())
        req.start()
        req.complete_synthesis()
        req.fulfill(uuid.uuid4())
        assert req.status == SynthesisRequestStatus.FULFILLED

    def test_events_through_lifecycle(self, ws_id):
        """Verify all expected events are emitted through full lifecycle."""
        req = _make_request(ws_id)
        req.submit()
        req.approve(uuid.uuid4())
        req.assign(_internal_assignment())
        req.start()
        req.complete_synthesis()
        req.fulfill(uuid.uuid4())

        events = req.collect_events()
        types = [type(e) for e in events]
        assert types == [
            SynthesisRequestCreated,
            SynthesisRequested,
            SynthesisRequestApproved,
            SynthesisRequestAssigned,
            SynthesisStarted,
            SynthesisCompleted,
            SynthesisRequestFulfilled,
        ]


# ---------------------------------------------------------------------------
# Submit
# ---------------------------------------------------------------------------


class TestSubmit:
    def test_submit_emits_event(self, ws_id):
        req = _make_request(ws_id)
        req.submit()
        events = req.collect_events()
        assert len(events) == 2
        assert events[0].__class__.__name__ == "SynthesisRequestCreated"
        assert isinstance(events[1], SynthesisRequested)
        assert events[1].molecule_id == req.molecule_id
        assert events[1].requester_id == req.requester_id
        assert events[1].requested_amount == 50.0
        assert events[1].priority == "routine"

    def test_submit_updates_timestamp(self, ws_id):
        req = _make_request(ws_id)
        old_ts = req.updated_at
        req.submit()
        assert req.updated_at >= old_ts


# ---------------------------------------------------------------------------
# Rejection
# ---------------------------------------------------------------------------


class TestRejection:
    def test_reject_from_submitted(self, ws_id):
        req = _make_request(ws_id)
        req.submit()
        rejector = uuid.uuid4()
        req.reject("Compound already available in stock", rejector)
        assert req.status == SynthesisRequestStatus.REJECTED
        assert req.rejection_reason == "Compound already available in stock"
        assert req.is_terminal is True

    def test_reject_emits_event(self, ws_id):
        req = _make_request(ws_id)
        req.submit()
        rejector = uuid.uuid4()
        req.reject("Budget exceeded", rejector)
        events = [e for e in req.collect_events() if isinstance(e, SynthesisRequestRejected)]
        assert len(events) == 1
        assert events[0].rejected_by == rejector
        assert events[0].reason == "Budget exceeded"

    def test_reject_empty_reason_raises(self, ws_id):
        req = _make_request(ws_id)
        req.submit()
        with pytest.raises(ValidationError, match="reason"):
            req.reject("   ", uuid.uuid4())

    def test_reject_from_approved_invalid(self, ws_id):
        req = _make_request(ws_id)
        req.submit()
        req.approve(uuid.uuid4())
        with pytest.raises(ValidationError, match="Cannot transition"):
            req.reject("Too late", uuid.uuid4())


# ---------------------------------------------------------------------------
# Cancellation
# ---------------------------------------------------------------------------


class TestCancellation:
    def test_cancel_from_submitted(self, ws_id):
        req = _make_request(ws_id)
        req.submit()
        req.cancel()
        assert req.status == SynthesisRequestStatus.CANCELLED
        assert req.is_terminal is True

    def test_cancel_from_approved(self, ws_id):
        req = _make_request(ws_id)
        req.submit()
        req.approve(uuid.uuid4())
        req.cancel()
        assert req.status == SynthesisRequestStatus.CANCELLED

    def test_cancel_from_assigned(self, ws_id):
        req = _make_request(ws_id)
        req.submit()
        req.approve(uuid.uuid4())
        req.assign(_internal_assignment())
        req.cancel()
        assert req.status == SynthesisRequestStatus.CANCELLED

    def test_cancel_no_event(self, ws_id):
        """Cancel does not emit a domain event."""
        req = _make_request(ws_id)
        req.submit()
        req.clear_events()
        req.cancel()
        assert len(req.collect_events()) == 0

    def test_cancel_from_in_progress_invalid(self, ws_id):
        req = _make_request(ws_id)
        req.submit()
        req.approve(uuid.uuid4())
        req.assign(_internal_assignment())
        req.start()
        with pytest.raises(ValidationError, match="Cannot transition"):
            req.cancel()

    def test_cancel_from_fulfilled_invalid(self, ws_id):
        req = _make_request(ws_id)
        req.submit()
        req.approve(uuid.uuid4())
        req.assign(_internal_assignment())
        req.start()
        req.complete_synthesis()
        req.fulfill(uuid.uuid4())
        with pytest.raises(ValidationError, match="Cannot transition"):
            req.cancel()


# ---------------------------------------------------------------------------
# Failure
# ---------------------------------------------------------------------------


class TestFailure:
    def test_fail_from_in_progress(self, ws_id):
        req = _make_request(ws_id)
        req.submit()
        req.approve(uuid.uuid4())
        req.assign(_internal_assignment())
        req.start()
        req.fail("Reaction did not proceed to completion")
        assert req.status == SynthesisRequestStatus.FAILED
        assert req.failure_reason == "Reaction did not proceed to completion"
        assert req.is_terminal is True

    def test_fail_emits_event(self, ws_id):
        req = _make_request(ws_id)
        req.submit()
        req.approve(uuid.uuid4())
        req.assign(_internal_assignment())
        req.start()
        req.fail("Side products dominated")
        events = [e for e in req.collect_events() if isinstance(e, SynthesisFailed)]
        assert len(events) == 1
        assert events[0].failure_reason == "Side products dominated"

    def test_fail_empty_reason_raises(self, ws_id):
        req = _make_request(ws_id)
        req.submit()
        req.approve(uuid.uuid4())
        req.assign(_internal_assignment())
        req.start()
        with pytest.raises(ValidationError, match="reason"):
            req.fail("   ")

    def test_fail_from_assigned_invalid(self, ws_id):
        req = _make_request(ws_id)
        req.submit()
        req.approve(uuid.uuid4())
        req.assign(_internal_assignment())
        with pytest.raises(ValidationError, match="Cannot transition"):
            req.fail("Not started yet")


# ---------------------------------------------------------------------------
# Flag infeasible
# ---------------------------------------------------------------------------


class TestFlagInfeasible:
    def test_flag_infeasible_returns_to_approved(self, ws_id):
        req = _make_request(ws_id)
        req.submit()
        req.approve(uuid.uuid4())
        req.assign(_internal_assignment())
        req.flag_infeasible(FeasibilityStatus.INFEASIBLE, "No viable route")
        assert req.status == SynthesisRequestStatus.APPROVED
        assert req.assignment is None
        assert req.feasibility_status == FeasibilityStatus.INFEASIBLE
        assert req.feasibility_notes == "No viable route"

    def test_flag_infeasible_emits_event(self, ws_id):
        req = _make_request(ws_id)
        req.submit()
        req.approve(uuid.uuid4())
        req.assign(_internal_assignment())
        req.flag_infeasible(FeasibilityStatus.CHALLENGING)
        events = [e for e in req.collect_events() if isinstance(e, SynthesisFeasibilityFlagged)]
        assert len(events) == 1
        assert events[0].feasibility_status == "challenging"

    def test_flag_infeasible_then_reassign(self, ws_id):
        """After infeasible flag, can be reassigned to a different chemist/CRO."""
        req = _make_request(ws_id)
        req.submit()
        req.approve(uuid.uuid4())
        req.assign(_internal_assignment())
        req.flag_infeasible(FeasibilityStatus.ALTERNATIVE_PROPOSED, "Try CRO")
        # Now back in approved, can be reassigned
        new_assignment = _cro_assignment()
        req.assign(new_assignment)
        assert req.status == SynthesisRequestStatus.ASSIGNED
        assert req.assignment == new_assignment

    def test_flag_infeasible_from_approved_invalid(self, ws_id):
        """Can only flag infeasible from assigned state."""
        req = _make_request(ws_id)
        req.submit()
        req.approve(uuid.uuid4())
        # flag_infeasible transitions to APPROVED, which is only valid from ASSIGNED
        with pytest.raises(ValidationError, match="Cannot transition"):
            req.flag_infeasible(FeasibilityStatus.INFEASIBLE)


# ---------------------------------------------------------------------------
# Assignment
# ---------------------------------------------------------------------------


class TestAssignment:
    def test_assign_internal(self, ws_id):
        req = _make_request(ws_id)
        req.submit()
        req.approve(uuid.uuid4())
        assignment = _internal_assignment()
        req.assign(assignment)
        assert req.status == SynthesisRequestStatus.ASSIGNED
        events = [e for e in req.collect_events() if isinstance(e, SynthesisRequestAssigned)]
        assert len(events) == 1
        assert events[0].assignment_type == "internal"
        assert events[0].assigned_to == assignment.assigned_to

    def test_assign_cro(self, ws_id):
        req = _make_request(ws_id)
        req.submit()
        req.approve(uuid.uuid4())
        assignment = _cro_assignment()
        req.assign(assignment)
        events = [e for e in req.collect_events() if isinstance(e, SynthesisRequestAssigned)]
        assert len(events) == 1
        assert events[0].assignment_type == "cro"
        assert events[0].assigned_org_id == assignment.assigned_org_id

    def test_assign_from_submitted_invalid(self, ws_id):
        req = _make_request(ws_id)
        req.submit()
        with pytest.raises(ValidationError, match="Cannot transition"):
            req.assign(_internal_assignment())


# ---------------------------------------------------------------------------
# Invalid transitions from terminal states
# ---------------------------------------------------------------------------


class TestTerminalStates:
    def test_fulfilled_is_terminal(self, ws_id):
        req = _make_request(ws_id)
        req.submit()
        req.approve(uuid.uuid4())
        req.assign(_internal_assignment())
        req.start()
        req.complete_synthesis()
        req.fulfill(uuid.uuid4())
        assert req.is_terminal is True

    def test_rejected_is_terminal(self, ws_id):
        req = _make_request(ws_id)
        req.submit()
        req.reject("No", uuid.uuid4())
        assert req.is_terminal is True

    def test_cancelled_is_terminal(self, ws_id):
        req = _make_request(ws_id)
        req.submit()
        req.cancel()
        assert req.is_terminal is True

    def test_failed_is_terminal(self, ws_id):
        req = _make_request(ws_id)
        req.submit()
        req.approve(uuid.uuid4())
        req.assign(_internal_assignment())
        req.start()
        req.fail("Decomposition")
        assert req.is_terminal is True

    def test_cannot_submit_from_fulfilled(self, ws_id):
        req = _make_request(ws_id)
        req.submit()
        req.approve(uuid.uuid4())
        req.assign(_internal_assignment())
        req.start()
        req.complete_synthesis()
        req.fulfill(uuid.uuid4())
        with pytest.raises(ValidationError, match="Cannot transition"):
            req.submit()

    def test_cannot_approve_from_rejected(self, ws_id):
        req = _make_request(ws_id)
        req.submit()
        req.reject("No", uuid.uuid4())
        with pytest.raises(ValidationError, match="Cannot transition"):
            req.approve(uuid.uuid4())

    def test_cannot_start_from_failed(self, ws_id):
        req = _make_request(ws_id)
        req.submit()
        req.approve(uuid.uuid4())
        req.assign(_internal_assignment())
        req.start()
        req.fail("Bad yield")
        with pytest.raises(ValidationError, match="Cannot transition"):
            req.start()


# ---------------------------------------------------------------------------
# Invalid transitions (non-terminal)
# ---------------------------------------------------------------------------


class TestInvalidTransitions:
    def test_cannot_approve_from_draft(self, ws_id):
        req = _make_request(ws_id)
        with pytest.raises(ValidationError, match="Cannot transition"):
            req.approve(uuid.uuid4())

    def test_cannot_assign_from_draft(self, ws_id):
        req = _make_request(ws_id)
        with pytest.raises(ValidationError, match="Cannot transition"):
            req.assign(_internal_assignment())

    def test_cannot_start_from_approved(self, ws_id):
        req = _make_request(ws_id)
        req.submit()
        req.approve(uuid.uuid4())
        with pytest.raises(ValidationError, match="Cannot transition"):
            req.start()

    def test_cannot_fulfill_from_in_progress(self, ws_id):
        req = _make_request(ws_id)
        req.submit()
        req.approve(uuid.uuid4())
        req.assign(_internal_assignment())
        req.start()
        with pytest.raises(ValidationError, match="Cannot transition"):
            req.fulfill(uuid.uuid4())

    def test_cannot_complete_from_assigned(self, ws_id):
        req = _make_request(ws_id)
        req.submit()
        req.approve(uuid.uuid4())
        req.assign(_internal_assignment())
        with pytest.raises(ValidationError, match="Cannot transition"):
            req.complete_synthesis()


# ---------------------------------------------------------------------------
# Non-transition mutators
# ---------------------------------------------------------------------------


class TestEstimatedFields:
    def test_set_estimated_cost(self, ws_id):
        req = _make_request(ws_id)
        cost = Amount(value=2000.0, unit=AmountUnit.G)
        old_ts = req.updated_at
        req.set_estimated_cost(cost)
        assert req.estimated_cost == cost
        assert req.updated_at >= old_ts

    def test_set_estimated_completion_date(self, ws_id):
        req = _make_request(ws_id)
        d = date(2026, 6, 15)
        req.set_estimated_completion_date(d)
        assert req.estimated_completion_date == d


# ---------------------------------------------------------------------------
# SynthesisAssignment VO validation
# ---------------------------------------------------------------------------


class TestSynthesisAssignmentVO:
    def test_internal_requires_assigned_to(self):
        with pytest.raises(ValueError, match="assigned_to"):
            SynthesisAssignment(
                assignment_type=AssignmentType.INTERNAL,
                assigned_to=None,
            )

    def test_cro_requires_org_id(self):
        with pytest.raises(ValueError, match="assigned_org_id"):
            SynthesisAssignment(
                assignment_type=AssignmentType.CRO,
                assigned_org_id=None,
            )

    def test_internal_valid(self):
        a = SynthesisAssignment(
            assignment_type=AssignmentType.INTERNAL,
            assigned_to=uuid.uuid4(),
        )
        assert a.assignment_type == AssignmentType.INTERNAL

    def test_cro_valid(self):
        a = SynthesisAssignment(
            assignment_type=AssignmentType.CRO,
            assigned_org_id=uuid.uuid4(),
        )
        assert a.assignment_type == AssignmentType.CRO
