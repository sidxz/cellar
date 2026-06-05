"""SampleRequest aggregate — formal request for compound material."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from cellar.domain.inventory.enums import RequestPriority, SampleRequestStatus
from cellar.domain.inventory.events import (
    SampleRequestApproved,
    SampleRequestCreated,
    SampleRequestFulfilled,
    SampleRequestRejected,
)
from cellar.domain.shared.entity import AggregateRoot
from cellar.domain.shared.errors import ValidationError
from cellar.domain.shared.value_objects import Amount

_VALID_TRANSITIONS: dict[SampleRequestStatus, set[SampleRequestStatus]] = {
    SampleRequestStatus.SUBMITTED: {
        SampleRequestStatus.APPROVED,
        SampleRequestStatus.REJECTED,
        SampleRequestStatus.CANCELLED,
    },
    SampleRequestStatus.APPROVED: {
        SampleRequestStatus.PREPARING,
        SampleRequestStatus.CANCELLED,
    },
    SampleRequestStatus.PREPARING: {
        SampleRequestStatus.FULFILLED,
        SampleRequestStatus.CANCELLED,
    },
    # Terminal states — no outgoing transitions
    SampleRequestStatus.FULFILLED: set(),
    SampleRequestStatus.REJECTED: set(),
    SampleRequestStatus.CANCELLED: set(),
}

_TERMINAL = {
    SampleRequestStatus.FULFILLED,
    SampleRequestStatus.REJECTED,
    SampleRequestStatus.CANCELLED,
}


class SampleRequest(AggregateRoot):
    """A formal request for compound material from existing stock."""

    def __init__(
        self,
        *,
        id: uuid.UUID | None = None,
        workspace_id: uuid.UUID,
        requester_id: uuid.UUID,
        molecule_id: uuid.UUID,
        batch_id: uuid.UUID | None = None,
        requested_amount: Amount,
        purpose: str,
        priority: RequestPriority = RequestPriority.ROUTINE,
        status: SampleRequestStatus = SampleRequestStatus.SUBMITTED,
        assigned_to: uuid.UUID | None = None,
        fulfilled_sample_id: uuid.UUID | None = None,
        rejection_reason: str | None = None,
        fulfilled_at: datetime | None = None,
        created_at: datetime | None = None,
        updated_at: datetime | None = None,
        version: int = 1,
    ) -> None:
        super().__init__(id=id, created_at=created_at, updated_at=updated_at, version=version)
        self.workspace_id = workspace_id
        self.requester_id = requester_id
        self.molecule_id = molecule_id
        self.batch_id = batch_id
        self.requested_amount = requested_amount
        self.purpose = purpose
        self.priority = priority
        self.status = status
        self.assigned_to = assigned_to
        self.fulfilled_sample_id = fulfilled_sample_id
        self.rejection_reason = rejection_reason
        self.fulfilled_at = fulfilled_at

    @property
    def is_terminal(self) -> bool:
        return self.status in _TERMINAL

    @classmethod
    def create(
        cls,
        *,
        workspace_id: uuid.UUID,
        requester_id: uuid.UUID,
        molecule_id: uuid.UUID,
        batch_id: uuid.UUID | None = None,
        requested_amount: Amount,
        purpose: str,
        priority: RequestPriority = RequestPriority.ROUTINE,
    ) -> SampleRequest:
        if requested_amount.value <= 0:
            raise ValidationError("Requested amount must be positive")
        if not purpose.strip():
            raise ValidationError("Purpose is required")

        request = cls(
            workspace_id=workspace_id,
            requester_id=requester_id,
            molecule_id=molecule_id,
            batch_id=batch_id,
            requested_amount=requested_amount,
            purpose=purpose,
            priority=priority,
        )
        request.register_event(
            SampleRequestCreated(
                aggregate_id=request.id,
                aggregate_type="SampleRequest",
                workspace_id=workspace_id,
                molecule_id=molecule_id,
                requester_id=requester_id,
                requested_amount=requested_amount.value,
                amount_unit=requested_amount.unit.value,
                priority=priority.value,
            )
        )
        return request

    # -- Mutable field updates --

    def update_details(
        self,
        *,
        purpose: str | None = ...,  # type: ignore[assignment]
        priority: RequestPriority | None = ...,  # type: ignore[assignment]
        requested_amount: Amount | None = ...,  # type: ignore[assignment]
    ) -> None:
        """Update mutable fields on a submitted request (sentinel pattern)."""
        if self.status != SampleRequestStatus.SUBMITTED:
            raise ValidationError("Can only update submitted sample requests")
        if purpose is not ...:
            if purpose is not None and not purpose.strip():
                raise ValidationError("Purpose is required")
            if purpose is not None:
                self.purpose = purpose
        if priority is not ... and priority is not None:
            self.priority = priority
        if requested_amount is not ... and requested_amount is not None:
            if requested_amount.value <= 0:
                raise ValidationError("Requested amount must be positive")
            self.requested_amount = requested_amount
        self.updated_at = datetime.now(UTC)

    # -- State transitions --

    def approve(self, assigned_to: uuid.UUID | None = None) -> None:
        self._assert_transition(SampleRequestStatus.APPROVED)
        self.status = SampleRequestStatus.APPROVED
        self.assigned_to = assigned_to
        self.updated_at = datetime.now(UTC)
        self.register_event(
            SampleRequestApproved(
                aggregate_id=self.id,
                aggregate_type="SampleRequest",
                workspace_id=self.workspace_id,
                assigned_to=assigned_to,
            )
        )

    def start_preparing(self) -> None:
        self._assert_transition(SampleRequestStatus.PREPARING)
        self.status = SampleRequestStatus.PREPARING
        self.updated_at = datetime.now(UTC)

    def fulfill(self, sample_id: uuid.UUID) -> None:
        self._assert_transition(SampleRequestStatus.FULFILLED)
        self.fulfilled_sample_id = sample_id
        self.fulfilled_at = datetime.now(UTC)
        self.status = SampleRequestStatus.FULFILLED
        self.updated_at = datetime.now(UTC)
        self.register_event(
            SampleRequestFulfilled(
                aggregate_id=self.id,
                aggregate_type="SampleRequest",
                workspace_id=self.workspace_id,
                fulfilled_sample_id=sample_id,
            )
        )

    def reject(self, reason: str) -> None:
        self._assert_transition(SampleRequestStatus.REJECTED)
        if not reason.strip():
            raise ValidationError("Rejection reason is required")
        self.rejection_reason = reason
        self.status = SampleRequestStatus.REJECTED
        self.updated_at = datetime.now(UTC)
        self.register_event(
            SampleRequestRejected(
                aggregate_id=self.id,
                aggregate_type="SampleRequest",
                workspace_id=self.workspace_id,
                reason=reason,
            )
        )

    def cancel(self) -> None:
        self._assert_transition(SampleRequestStatus.CANCELLED)
        self.status = SampleRequestStatus.CANCELLED
        self.updated_at = datetime.now(UTC)

    def _assert_transition(self, target: SampleRequestStatus) -> None:
        allowed = _VALID_TRANSITIONS.get(self.status, set())
        if target not in allowed:
            raise ValidationError(f"Cannot transition from {self.status.value} to {target.value}")
