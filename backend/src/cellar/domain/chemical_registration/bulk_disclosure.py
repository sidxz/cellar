"""BulkDisclosure aggregate root — groups multiple DisclosureRequests from a single file upload."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from cellar.domain.chemical_registration.enums import BulkDisclosureStatus
from cellar.domain.chemical_registration.events import (
    BulkDisclosureCompleted,
    BulkDisclosureStarted,
)
from cellar.domain.shared.entity import AggregateRoot
from cellar.domain.shared.errors import ValidationError

# ---------------------------------------------------------------------------
# State-machine transition table
# ---------------------------------------------------------------------------

_BULK_TRANSITIONS: dict[BulkDisclosureStatus, set[BulkDisclosureStatus]] = {
    BulkDisclosureStatus.PENDING: {BulkDisclosureStatus.PROCESSING},
    BulkDisclosureStatus.PROCESSING: {
        BulkDisclosureStatus.COMPLETED,
        BulkDisclosureStatus.COMPLETED_WITH_ERRORS,
    },
    BulkDisclosureStatus.COMPLETED: set(),
    BulkDisclosureStatus.COMPLETED_WITH_ERRORS: set(),
}


class BulkDisclosure(AggregateRoot):
    """A bulk disclosure operation that tracks progress across multiple disclosure requests.

    State machine::

        pending -> processing -> completed              (all items disclosed/merged)
        pending -> processing -> completed_with_errors  (some conflicts or errors)
    """

    def __init__(
        self,
        *,
        id: uuid.UUID | None = None,
        workspace_id: uuid.UUID,
        source_file: str,
        partner_org_id: uuid.UUID,
        submitted_by: uuid.UUID,
        submitted_at: datetime | None = None,
        status: BulkDisclosureStatus = BulkDisclosureStatus.PENDING,
        total_count: int,
        disclosed_count: int = 0,
        merged_count: int = 0,
        conflict_count: int = 0,
        error_count: int = 0,
        completed_at: datetime | None = None,
        created_at: datetime | None = None,
        updated_at: datetime | None = None,
        version: int = 1,
    ) -> None:
        super().__init__(id=id, created_at=created_at, updated_at=updated_at, version=version)

        if not source_file or not source_file.strip():
            raise ValidationError("source_file must not be empty")
        if total_count <= 0:
            raise ValidationError("total_count must be greater than zero")

        self.workspace_id = workspace_id
        self.source_file = source_file.strip()
        self.partner_org_id = partner_org_id
        self.submitted_by = submitted_by
        self.submitted_at = submitted_at or datetime.now(UTC)
        self.status = status
        self.total_count = total_count
        self.disclosed_count = disclosed_count
        self.merged_count = merged_count
        self.conflict_count = conflict_count
        self.error_count = error_count
        self.completed_at = completed_at

    # ------------------------------------------------------------------
    # Factory method
    # ------------------------------------------------------------------

    @classmethod
    def create(
        cls,
        *,
        workspace_id: uuid.UUID,
        source_file: str,
        partner_org_id: uuid.UUID,
        submitted_by: uuid.UUID,
        total_count: int,
    ) -> BulkDisclosure:
        """Create a new bulk disclosure in PENDING status."""
        bd = cls(
            workspace_id=workspace_id,
            source_file=source_file,
            partner_org_id=partner_org_id,
            submitted_by=submitted_by,
            total_count=total_count,
        )
        bd.register_event(
            BulkDisclosureStarted(
                aggregate_id=bd.id,
                aggregate_type="BulkDisclosure",
                workspace_id=workspace_id,
                source_file=source_file,
                partner_org_id=partner_org_id,
                total_count=total_count,
                submitted_by=submitted_by,
            )
        )
        return bd

    # ------------------------------------------------------------------
    # Computed property
    # ------------------------------------------------------------------

    @property
    def processed_count(self) -> int:
        """Total items processed so far."""
        return self.disclosed_count + self.merged_count + self.conflict_count + self.error_count

    # ------------------------------------------------------------------
    # State transitions
    # ------------------------------------------------------------------

    def _guard_transition(self, target: BulkDisclosureStatus) -> None:
        """Validate the state transition is allowed."""
        allowed = _BULK_TRANSITIONS.get(self.status, set())
        if target not in allowed:
            raise ValidationError(
                f"Cannot transition bulk disclosure status from '{self.status}' to '{target}'"
            )

    def _guard_processing(self) -> None:
        """Ensure the bulk disclosure is in PROCESSING status."""
        if self.status != BulkDisclosureStatus.PROCESSING:
            raise ValidationError("Can only record results while bulk disclosure is processing")

    def start_processing(self) -> None:
        """PENDING -> PROCESSING."""
        self._guard_transition(BulkDisclosureStatus.PROCESSING)
        self.status = BulkDisclosureStatus.PROCESSING
        self.updated_at = datetime.now(UTC)

    def record_disclosed(self) -> None:
        """Increment disclosed_count (must be PROCESSING)."""
        self._guard_processing()
        self.disclosed_count += 1
        self.updated_at = datetime.now(UTC)

    def record_merged(self) -> None:
        """Increment merged_count (must be PROCESSING)."""
        self._guard_processing()
        self.merged_count += 1
        self.updated_at = datetime.now(UTC)

    def record_conflict(self) -> None:
        """Increment conflict_count (must be PROCESSING)."""
        self._guard_processing()
        self.conflict_count += 1
        self.updated_at = datetime.now(UTC)

    def record_error(self) -> None:
        """Increment error_count (must be PROCESSING)."""
        self._guard_processing()
        self.error_count += 1
        self.updated_at = datetime.now(UTC)

    def complete(self) -> None:
        """PROCESSING -> COMPLETED or COMPLETED_WITH_ERRORS.

        Requires processed_count == total_count.
        Uses COMPLETED_WITH_ERRORS if conflict_count > 0 or error_count > 0.
        """
        if self.processed_count != self.total_count:
            raise ValidationError(
                f"Cannot complete: processed {self.processed_count} of {self.total_count} items"
            )

        has_issues = self.conflict_count > 0 or self.error_count > 0
        target = (
            BulkDisclosureStatus.COMPLETED_WITH_ERRORS
            if has_issues
            else BulkDisclosureStatus.COMPLETED
        )

        self._guard_transition(target)
        self.status = target
        self.completed_at = datetime.now(UTC)
        self.updated_at = datetime.now(UTC)
        self.register_event(
            BulkDisclosureCompleted(
                aggregate_id=self.id,
                aggregate_type="BulkDisclosure",
                workspace_id=self.workspace_id,
                disclosed_count=self.disclosed_count,
                merged_count=self.merged_count,
                conflict_count=self.conflict_count,
                error_count=self.error_count,
            )
        )
