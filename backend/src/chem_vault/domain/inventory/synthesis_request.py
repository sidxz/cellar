"""SynthesisRequest aggregate — 10-state machine for compound synthesis requests."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime

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
    SynthesisRequestFulfilled,
    SynthesisRequestRejected,
    SynthesisRequested,
    SynthesisStarted,
)
from chem_vault.domain.shared.entity import AggregateRoot
from chem_vault.domain.shared.errors import ValidationError
from chem_vault.domain.shared.value_objects import Amount, ChemicalStructure, SynthesisAssignment


# ---------------------------------------------------------------------------
# State machine
# ---------------------------------------------------------------------------

_VALID_TRANSITIONS: dict[SynthesisRequestStatus, set[SynthesisRequestStatus]] = {
    SynthesisRequestStatus.DRAFT: {
        SynthesisRequestStatus.SUBMITTED,
    },
    SynthesisRequestStatus.SUBMITTED: {
        SynthesisRequestStatus.APPROVED,
        SynthesisRequestStatus.REJECTED,
        SynthesisRequestStatus.CANCELLED,
    },
    SynthesisRequestStatus.APPROVED: {
        SynthesisRequestStatus.ASSIGNED,
        SynthesisRequestStatus.CANCELLED,
    },
    SynthesisRequestStatus.ASSIGNED: {
        SynthesisRequestStatus.IN_PROGRESS,
        SynthesisRequestStatus.APPROVED,  # flag_infeasible returns for reassignment
        SynthesisRequestStatus.CANCELLED,
    },
    SynthesisRequestStatus.IN_PROGRESS: {
        SynthesisRequestStatus.SYNTHESIS_COMPLETE,
        SynthesisRequestStatus.FAILED,
    },
    SynthesisRequestStatus.SYNTHESIS_COMPLETE: {
        SynthesisRequestStatus.FULFILLED,
    },
    # Terminal states — no outgoing transitions
    SynthesisRequestStatus.FULFILLED: set(),
    SynthesisRequestStatus.REJECTED: set(),
    SynthesisRequestStatus.CANCELLED: set(),
    SynthesisRequestStatus.FAILED: set(),
}

_TERMINAL = {
    SynthesisRequestStatus.FULFILLED,
    SynthesisRequestStatus.REJECTED,
    SynthesisRequestStatus.CANCELLED,
    SynthesisRequestStatus.FAILED,
}


class SynthesisRequest(AggregateRoot):
    """A formal request for de-novo compound synthesis.

    10-state lifecycle:
        draft -> submitted -> approved -> assigned -> in_progress
            -> synthesis_complete -> fulfilled

    With branches:
        submitted -> rejected (terminal)
        submitted/approved/assigned -> cancelled (terminal)
        in_progress -> failed (terminal)
        assigned -> approved (infeasible flag, returns for reassignment)
    """

    def __init__(
        self,
        *,
        id: uuid.UUID | None = None,
        workspace_id: uuid.UUID,
        requester_id: uuid.UUID,
        molecule_id: uuid.UUID,
        target_structure: ChemicalStructure | None = None,
        requested_amount: Amount,
        target_purity: float | None = None,
        purpose: str,
        priority: RequestPriority = RequestPriority.ROUTINE,
        status: SynthesisRequestStatus = SynthesisRequestStatus.DRAFT,
        project_id: uuid.UUID | None = None,
        approved_by: uuid.UUID | None = None,
        approved_at: datetime | None = None,
        rejection_reason: str | None = None,
        assignment: SynthesisAssignment | None = None,
        proposed_route_id: uuid.UUID | None = None,
        feasibility_notes: str | None = None,
        feasibility_status: FeasibilityStatus | None = None,
        estimated_cost: Amount | None = None,
        actual_cost: Amount | None = None,
        estimated_completion_date: date | None = None,
        actual_completion_date: date | None = None,
        fulfilled_batch_id: uuid.UUID | None = None,
        failure_reason: str | None = None,
        parent_request_id: uuid.UUID | None = None,
        bulk_request_id: uuid.UUID | None = None,
        created_at: datetime | None = None,
        updated_at: datetime | None = None,
        version: int = 1,
    ) -> None:
        super().__init__(id=id, created_at=created_at, updated_at=updated_at, version=version)
        self.workspace_id = workspace_id
        self.requester_id = requester_id
        self.molecule_id = molecule_id
        self.target_structure = target_structure
        self.requested_amount = requested_amount
        self.target_purity = target_purity
        self.purpose = purpose
        self.priority = priority
        self.status = status
        self.project_id = project_id
        self.approved_by = approved_by
        self.approved_at = approved_at
        self.rejection_reason = rejection_reason
        self.assignment = assignment
        self.proposed_route_id = proposed_route_id
        self.feasibility_notes = feasibility_notes
        self.feasibility_status = feasibility_status
        self.estimated_cost = estimated_cost
        self.actual_cost = actual_cost
        self.estimated_completion_date = estimated_completion_date
        self.actual_completion_date = actual_completion_date
        self.fulfilled_batch_id = fulfilled_batch_id
        self.failure_reason = failure_reason
        self.parent_request_id = parent_request_id
        self.bulk_request_id = bulk_request_id

    # -- Properties --

    @property
    def is_terminal(self) -> bool:
        return self.status in _TERMINAL

    # -- Factory --

    @classmethod
    def create(
        cls,
        *,
        workspace_id: uuid.UUID,
        requester_id: uuid.UUID,
        molecule_id: uuid.UUID,
        target_structure: ChemicalStructure | None = None,
        requested_amount: Amount,
        target_purity: float | None = None,
        purpose: str,
        priority: RequestPriority = RequestPriority.ROUTINE,
        project_id: uuid.UUID | None = None,
        parent_request_id: uuid.UUID | None = None,
        bulk_request_id: uuid.UUID | None = None,
    ) -> SynthesisRequest:
        """Create a new synthesis request in DRAFT status.

        Validates:
        - requested_amount.value > 0
        - purpose is non-empty
        - target_purity in (0, 100] if set
        """
        if requested_amount.value <= 0:
            raise ValidationError("Requested amount must be positive")
        if not purpose.strip():
            raise ValidationError("Purpose is required")
        if target_purity is not None:
            if target_purity <= 0 or target_purity > 100:
                raise ValidationError("Target purity must be in (0, 100]")

        return cls(
            workspace_id=workspace_id,
            requester_id=requester_id,
            molecule_id=molecule_id,
            target_structure=target_structure,
            requested_amount=requested_amount,
            target_purity=target_purity,
            purpose=purpose,
            priority=priority,
            project_id=project_id,
            parent_request_id=parent_request_id,
            bulk_request_id=bulk_request_id,
        )

    # -- State transitions --

    def submit(self) -> None:
        """Draft -> submitted. Emits SynthesisRequested."""
        self._assert_transition(SynthesisRequestStatus.SUBMITTED)
        self.status = SynthesisRequestStatus.SUBMITTED
        self.updated_at = datetime.now(UTC)
        self.register_event(
            SynthesisRequested(
                aggregate_id=self.id,
                aggregate_type="SynthesisRequest",
                molecule_id=self.molecule_id,
                requester_id=self.requester_id,
                requested_amount=self.requested_amount.value,
                amount_unit=self.requested_amount.unit.value,
                priority=self.priority.value,
            )
        )

    def approve(self, approved_by: uuid.UUID) -> None:
        """Submitted -> approved."""
        self._assert_transition(SynthesisRequestStatus.APPROVED)
        self.approved_by = approved_by
        self.approved_at = datetime.now(UTC)
        self.status = SynthesisRequestStatus.APPROVED
        self.updated_at = datetime.now(UTC)
        self.register_event(
            SynthesisRequestApproved(
                aggregate_id=self.id,
                aggregate_type="SynthesisRequest",
                approved_by=approved_by,
            )
        )

    def reject(self, reason: str, rejected_by: uuid.UUID) -> None:
        """Submitted -> rejected (terminal)."""
        self._assert_transition(SynthesisRequestStatus.REJECTED)
        if not reason.strip():
            raise ValidationError("Rejection reason is required")
        self.rejection_reason = reason
        self.status = SynthesisRequestStatus.REJECTED
        self.updated_at = datetime.now(UTC)
        self.register_event(
            SynthesisRequestRejected(
                aggregate_id=self.id,
                aggregate_type="SynthesisRequest",
                rejected_by=rejected_by,
                reason=reason,
            )
        )

    def assign(self, assignment: SynthesisAssignment) -> None:
        """Approved -> assigned."""
        self._assert_transition(SynthesisRequestStatus.ASSIGNED)
        self.assignment = assignment
        self.status = SynthesisRequestStatus.ASSIGNED
        self.updated_at = datetime.now(UTC)
        self.register_event(
            SynthesisRequestAssigned(
                aggregate_id=self.id,
                aggregate_type="SynthesisRequest",
                assignment_type=assignment.assignment_type.value,
                assigned_to=assignment.assigned_to,
                assigned_org_id=assignment.assigned_org_id,
            )
        )

    def start(self, proposed_route_id: uuid.UUID | None = None) -> None:
        """Assigned -> in_progress."""
        self._assert_transition(SynthesisRequestStatus.IN_PROGRESS)
        self.proposed_route_id = proposed_route_id
        self.status = SynthesisRequestStatus.IN_PROGRESS
        self.updated_at = datetime.now(UTC)
        self.register_event(
            SynthesisStarted(
                aggregate_id=self.id,
                aggregate_type="SynthesisRequest",
                proposed_route_id=proposed_route_id,
            )
        )

    def flag_infeasible(
        self,
        feasibility_status: FeasibilityStatus,
        feasibility_notes: str | None = None,
    ) -> None:
        """Assigned -> approved (returns for reassignment, clears assignment)."""
        self._assert_transition(SynthesisRequestStatus.APPROVED)
        self.feasibility_status = feasibility_status
        self.feasibility_notes = feasibility_notes
        self.assignment = None
        self.status = SynthesisRequestStatus.APPROVED
        self.updated_at = datetime.now(UTC)
        self.register_event(
            SynthesisFeasibilityFlagged(
                aggregate_id=self.id,
                aggregate_type="SynthesisRequest",
                feasibility_status=feasibility_status.value,
                feasibility_notes=feasibility_notes,
            )
        )

    def complete_synthesis(self, actual_cost: Amount | None = None) -> None:
        """In_progress -> synthesis_complete."""
        self._assert_transition(SynthesisRequestStatus.SYNTHESIS_COMPLETE)
        self.actual_cost = actual_cost
        self.actual_completion_date = datetime.now(UTC).date()
        self.status = SynthesisRequestStatus.SYNTHESIS_COMPLETE
        self.updated_at = datetime.now(UTC)
        self.register_event(
            SynthesisCompleted(
                aggregate_id=self.id,
                aggregate_type="SynthesisRequest",
                actual_cost_value=actual_cost.value if actual_cost else None,
                actual_cost_unit=actual_cost.unit.value if actual_cost else None,
            )
        )

    def fulfill(self, batch_id: uuid.UUID) -> None:
        """Synthesis_complete -> fulfilled (terminal)."""
        self._assert_transition(SynthesisRequestStatus.FULFILLED)
        self.fulfilled_batch_id = batch_id
        self.status = SynthesisRequestStatus.FULFILLED
        self.updated_at = datetime.now(UTC)
        self.register_event(
            SynthesisRequestFulfilled(
                aggregate_id=self.id,
                aggregate_type="SynthesisRequest",
                fulfilled_batch_id=batch_id,
            )
        )

    def fail(self, reason: str) -> None:
        """In_progress -> failed (terminal)."""
        self._assert_transition(SynthesisRequestStatus.FAILED)
        if not reason.strip():
            raise ValidationError("Failure reason is required")
        self.failure_reason = reason
        self.status = SynthesisRequestStatus.FAILED
        self.updated_at = datetime.now(UTC)
        self.register_event(
            SynthesisFailed(
                aggregate_id=self.id,
                aggregate_type="SynthesisRequest",
                failure_reason=reason,
            )
        )

    def cancel(self) -> None:
        """Submitted/approved/assigned -> cancelled (terminal). No event emitted."""
        self._assert_transition(SynthesisRequestStatus.CANCELLED)
        self.status = SynthesisRequestStatus.CANCELLED
        self.updated_at = datetime.now(UTC)

    # -- Non-transition mutators --

    def set_estimated_cost(self, cost: Amount) -> None:
        """Set the estimated cost for this synthesis."""
        self.estimated_cost = cost
        self.updated_at = datetime.now(UTC)

    def set_estimated_completion_date(self, d: date) -> None:
        """Set the estimated completion date."""
        self.estimated_completion_date = d
        self.updated_at = datetime.now(UTC)

    # -- Internals --

    def _assert_transition(self, target: SynthesisRequestStatus) -> None:
        allowed = _VALID_TRANSITIONS.get(self.status, set())
        if target not in allowed:
            raise ValidationError(
                f"Cannot transition from {self.status.value} to {target.value}"
            )
