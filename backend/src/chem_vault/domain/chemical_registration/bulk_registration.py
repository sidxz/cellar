"""BulkRegistration aggregate root — groups multiple molecule registrations from a single file upload."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from chem_vault.domain.chemical_registration.enums import (
    BulkRegistrationFileFormat,
    BulkRegistrationItemAction,
    BulkRegistrationStatus,
)
from chem_vault.domain.chemical_registration.events import (
    BulkRegistrationCompleted,
    BulkRegistrationStarted,
)
from chem_vault.domain.shared.entity import AggregateRoot, Entity
from chem_vault.domain.shared.errors import ValidationError


class BulkRegistrationItem(Entity):
    """Per-row outcome of a bulk registration — append-only child of BulkRegistration.

    Each row in the source file produces exactly one item once processed. The
    item records what happened (action), its identifiers when registration
    succeeded, or the error message when it failed. Used for the summary view
    so users can see *which* compound failed and why.
    """

    def __init__(
        self,
        *,
        id: uuid.UUID | None = None,
        bulk_registration_id: uuid.UUID,
        workspace_id: uuid.UUID,
        row_index: int,
        action: BulkRegistrationItemAction,
        success: bool,
        molecule_id: uuid.UUID | None = None,
        molecule_name: str | None = None,
        registration_number: str | None = None,
        batch_id: uuid.UUID | None = None,
        batch_number: str | None = None,
        error: str | None = None,
        created_at: datetime | None = None,
    ) -> None:
        super().__init__(id=id, created_at=created_at, updated_at=created_at)

        if row_index < 0:
            raise ValidationError("row_index must be non-negative")
        if success and action == BulkRegistrationItemAction.ERROR:
            raise ValidationError("action=error is incompatible with success=True")
        if not success and action != BulkRegistrationItemAction.ERROR:
            raise ValidationError(
                "non-error action requires success=True"
            )
        if action == BulkRegistrationItemAction.ERROR and not error:
            raise ValidationError("error message is required for action=error")

        self.bulk_registration_id = bulk_registration_id
        self.workspace_id = workspace_id
        self.row_index = row_index
        self.action = action
        self.success = success
        self.molecule_id = molecule_id
        self.molecule_name = molecule_name
        self.registration_number = registration_number
        self.batch_id = batch_id
        self.batch_number = batch_number
        self.error = error

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
        workflow_id: str | None = None,
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
        self.workflow_id = workflow_id
        self.status = status
        self.total_count = total_count
        self.registered_count = registered_count
        self.duplicate_count = duplicate_count
        self.error_count = error_count
        self.completed_at = completed_at
        self._pending_items: list[BulkRegistrationItem] = []

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
        workflow_id: str | None = None,
    ) -> BulkRegistration:
        """Create a new bulk registration in PENDING status."""
        bulk = cls(
            workspace_id=workspace_id,
            source_file=source_file,
            file_format=file_format,
            submitted_by=submitted_by,
            total_count=total_count,
            workflow_id=workflow_id,
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

    # ------------------------------------------------------------------
    # Per-row item recording (append-only)
    # ------------------------------------------------------------------

    def record_item(
        self,
        *,
        row_index: int,
        action: BulkRegistrationItemAction,
        molecule_id: uuid.UUID | None = None,
        molecule_name: str | None = None,
        registration_number: str | None = None,
        batch_id: uuid.UUID | None = None,
        batch_number: str | None = None,
        error: str | None = None,
    ) -> BulkRegistrationItem:
        """Append a per-row outcome and increment the matching counter.

        Items appended here are flushed to storage by the repository on save.
        Counters are kept in sync so callers do NOT separately call
        record_registered/duplicate/error — record_item is the single entry
        point when per-row provenance is being tracked.
        """
        self._guard_processing()

        success = action != BulkRegistrationItemAction.ERROR
        item = BulkRegistrationItem(
            bulk_registration_id=self.id,
            workspace_id=self.workspace_id,
            row_index=row_index,
            action=action,
            success=success,
            molecule_id=molecule_id,
            molecule_name=molecule_name,
            registration_number=registration_number,
            batch_id=batch_id,
            batch_number=batch_number,
            error=error,
        )
        self._pending_items.append(item)

        # Roll up to aggregate counters. duplicate_count covers the
        # "same molecule already existed" cases (deduplicated, disclosed
        # against an existing molecule, merge_candidate awaiting review,
        # conflict — all do NOT add new molecules). error_count is errors,
        # registered_count is brand-new molecule rows.
        if action == BulkRegistrationItemAction.REGISTERED:
            self.registered_count += 1
        elif action == BulkRegistrationItemAction.ERROR:
            self.error_count += 1
        else:
            self.duplicate_count += 1

        self.updated_at = datetime.now(UTC)
        return item

    def collect_pending_items(self) -> list[BulkRegistrationItem]:
        """Return queued items for the repository to flush; clears the queue."""
        items = list(self._pending_items)
        self._pending_items.clear()
        return items

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
                workspace_id=self.workspace_id,
                registered_count=self.registered_count,
                duplicate_count=self.duplicate_count,
                error_count=self.error_count,
            )
        )
