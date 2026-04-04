"""BulkRegistration aggregate root — groups multiple molecule registrations from a single file upload."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from chem_vault.domain.chemical_registration.enums import (
    BulkRegistrationFileFormat,
    BulkRegistrationStatus,
)
from chem_vault.domain.chemical_registration.events import (
    BulkRegistrationCompleted,
    BulkRegistrationStarted,
)
from chem_vault.domain.shared.entity import AggregateRoot
from chem_vault.domain.shared.errors import ValidationError

# ---------------------------------------------------------------------------
# State-machine transition table
# ---------------------------------------------------------------------------

_BULK_REG_TRANSITIONS: dict[BulkRegistrationStatus, set[BulkRegistrationStatus]] = {
    BulkRegistrationStatus.PENDING: {BulkRegistrationStatus.PROCESSING},
    BulkRegistrationStatus.PROCESSING: {
        BulkRegistrationStatus.COMPLETED,
        BulkRegistrationStatus.COMPLETED_WITH_ERRORS,
    },
    BulkRegistrationStatus.COMPLETED: set(),
    BulkRegistrationStatus.COMPLETED_WITH_ERRORS: set(),
}


class BulkRegistration(AggregateRoot):
    """A bulk registration operation that tracks progress across multiple molecule registrations.

    State machine::

        pending -> processing -> completed              (all items registered or duplicated)
        pending -> processing -> completed_with_errors  (some items had errors)

    Invariants:
        - total_count > 0
        - When completed: total_count = registered_count + duplicate_count + error_count
        - Items processed sequentially (earlier items affect dedup for later ones)
    """

    def __init__(
        self,
        *,
        id: uuid.UUID | None = None,
        workspace_id: uuid.UUID,
        source_file: str,
        file_format: BulkRegistrationFileFormat,
        submitted_by: uuid.UUID,
        submitted_at: datetime | None = None,
        status: BulkRegistrationStatus = BulkRegistrationStatus.PENDING,
        total_count: int,
        registered_count: int = 0,
        duplicate_count: int = 0,
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
        self.file_format = file_format
        self.submitted_by = submitted_by
        self.submitted_at = submitted_at or datetime.now(UTC)
        self.status = status
        self.total_count = total_count
        self.registered_count = registered_count
        self.duplicate_count = duplicate_count
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
        file_format: BulkRegistrationFileFormat,
        submitted_by: uuid.UUID,
        total_count: int,
    ) -> BulkRegistration:
        """Create a new bulk registration in PENDING status."""
        bulk = cls(
            workspace_id=workspace_id,
            source_file=source_file,
            file_format=file_format,
            submitted_by=submitted_by,
            total_count=total_count,
        )
        bulk.register_event(
            BulkRegistrationStarted(
                aggregate_id=bulk.id,
                aggregate_type="BulkRegistration",
                workspace_id=workspace_id,
                source_file=source_file,
                file_format=file_format.value,
                total_count=total_count,
                submitted_by=submitted_by,
            )
        )
        return bulk

    # ------------------------------------------------------------------
    # Computed property
    # ------------------------------------------------------------------

    @property
    def processed_count(self) -> int:
        """Total items processed so far."""
        return self.registered_count + self.duplicate_count + self.error_count

    # ------------------------------------------------------------------
    # State transitions
    # ------------------------------------------------------------------

    def _guard_transition(self, target: BulkRegistrationStatus) -> None:
        allowed = _BULK_REG_TRANSITIONS.get(self.status, set())
        if target not in allowed:
            raise ValidationError(
                f"Cannot transition bulk registration status from "
                f"'{self.status}' to '{target}'"
            )

    def _guard_processing(self) -> None:
        if self.status != BulkRegistrationStatus.PROCESSING:
            raise ValidationError(
                "Can only record results while bulk registration is processing"
            )

    def start_processing(self) -> None:
        """PENDING -> PROCESSING."""
        self._guard_transition(BulkRegistrationStatus.PROCESSING)
        self.status = BulkRegistrationStatus.PROCESSING
        self.updated_at = datetime.now(UTC)

    def record_registered(self) -> None:
        """Increment registered_count (must be PROCESSING)."""
        self._guard_processing()
        self.registered_count += 1
        self.updated_at = datetime.now(UTC)

    def record_duplicate(self) -> None:
        """Increment duplicate_count (must be PROCESSING)."""
        self._guard_processing()
        self.duplicate_count += 1
        self.updated_at = datetime.now(UTC)

    def record_error(self) -> None:
        """Increment error_count (must be PROCESSING)."""
        self._guard_processing()
        self.error_count += 1
        self.updated_at = datetime.now(UTC)

    def complete(self) -> None:
        """PROCESSING -> COMPLETED or COMPLETED_WITH_ERRORS.

        Requires processed_count == total_count.
        Uses COMPLETED_WITH_ERRORS if error_count > 0.
        """
        if self.processed_count != self.total_count:
            raise ValidationError(
                f"Cannot complete: processed {self.processed_count} of "
                f"{self.total_count} items"
            )

        target = (
            BulkRegistrationStatus.COMPLETED_WITH_ERRORS
            if self.error_count > 0
            else BulkRegistrationStatus.COMPLETED
        )

        self._guard_transition(target)
        self.status = target
        self.completed_at = datetime.now(UTC)
        self.updated_at = datetime.now(UTC)
        self.register_event(
            BulkRegistrationCompleted(
                aggregate_id=self.id,
                aggregate_type="BulkRegistration",
                registered_count=self.registered_count,
                duplicate_count=self.duplicate_count,
                error_count=self.error_count,
            )
        )
