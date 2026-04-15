"""CddPlateImport aggregate root — tracks import of plates from a CDD Vault."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from chem_vault.domain.inventory.enums import CddPlateImportStatus
from chem_vault.domain.inventory.events import (
    CddPlateImportCompleted,
    CddPlateImportDiscoveryComplete,
    CddPlateImportFailed,
    CddPlateImportStarted,
)
from chem_vault.domain.shared.entity import AggregateRoot
from chem_vault.domain.shared.errors import ValidationError

# ---------------------------------------------------------------------------
# State-machine transition table
# ---------------------------------------------------------------------------

_TRANSITIONS: dict[CddPlateImportStatus, set[CddPlateImportStatus]] = {
    CddPlateImportStatus.PENDING: {CddPlateImportStatus.DISCOVERING},
    CddPlateImportStatus.DISCOVERING: {
        CddPlateImportStatus.PROCESSING,
        CddPlateImportStatus.FAILED,
    },
    CddPlateImportStatus.PROCESSING: {
        CddPlateImportStatus.COMPLETED,
        CddPlateImportStatus.COMPLETED_WITH_ERRORS,
        CddPlateImportStatus.FAILED,
    },
    CddPlateImportStatus.COMPLETED: set(),
    CddPlateImportStatus.COMPLETED_WITH_ERRORS: set(),
    CddPlateImportStatus.FAILED: set(),
}


class CddPlateImport(AggregateRoot):
    """Import operation that pulls plates from an external CDD Vault.

    State machine::

        pending -> discovering -> processing -> completed
                                             -> completed_with_errors
                   discovering -> failed  (auth error, vault not found)
                                 processing -> failed  (unrecoverable)

    Invariants:
        - cdd_vault_id must not be empty
        - total_count is set after discovery
    """

    def __init__(
        self,
        *,
        id: uuid.UUID | None = None,
        workspace_id: uuid.UUID,
        cdd_vault_id: str,
        status: CddPlateImportStatus = CddPlateImportStatus.PENDING,
        workflow_id: str | None = None,
        total_count: int = 0,
        plates_registered: int = 0,
        plates_duplicate: int = 0,
        plates_error: int = 0,
        wells_mapped: int = 0,
        wells_unresolved: int = 0,
        last_processed_offset: int = 0,
        submitted_by: uuid.UUID,
        submitted_at: datetime | None = None,
        completed_at: datetime | None = None,
        created_at: datetime | None = None,
        updated_at: datetime | None = None,
        version: int = 1,
    ) -> None:
        super().__init__(id=id, created_at=created_at, updated_at=updated_at, version=version)

        if not cdd_vault_id or not cdd_vault_id.strip():
            raise ValidationError("cdd_vault_id must not be empty")

        self.workspace_id = workspace_id
        self.cdd_vault_id = cdd_vault_id.strip()
        self.status = status
        self.workflow_id = workflow_id
        self.total_count = total_count
        self.plates_registered = plates_registered
        self.plates_duplicate = plates_duplicate
        self.plates_error = plates_error
        self.wells_mapped = wells_mapped
        self.wells_unresolved = wells_unresolved
        self.last_processed_offset = last_processed_offset
        self.submitted_by = submitted_by
        self.submitted_at = submitted_at or datetime.now(UTC)
        self.completed_at = completed_at

    # ------------------------------------------------------------------
    # Factory method
    # ------------------------------------------------------------------

    @classmethod
    def create(
        cls,
        *,
        workspace_id: uuid.UUID,
        cdd_vault_id: str,
        submitted_by: uuid.UUID,
        workflow_id: str | None = None,
    ) -> CddPlateImport:
        """Create a new plate import in PENDING status."""
        imp = cls(
            workspace_id=workspace_id,
            cdd_vault_id=cdd_vault_id,
            submitted_by=submitted_by,
            workflow_id=workflow_id,
        )
        imp.register_event(
            CddPlateImportStarted(
                aggregate_id=imp.id,
                aggregate_type="CddPlateImport",
                workspace_id=workspace_id,
                cdd_vault_id=cdd_vault_id,
                submitted_by=submitted_by,
            )
        )
        return imp

    # ------------------------------------------------------------------
    # Computed property
    # ------------------------------------------------------------------

    @property
    def processed_count(self) -> int:
        return self.plates_registered + self.plates_duplicate + self.plates_error

    # ------------------------------------------------------------------
    # State transitions
    # ------------------------------------------------------------------

    def _guard_transition(self, target: CddPlateImportStatus) -> None:
        allowed = _TRANSITIONS.get(self.status, set())
        if target not in allowed:
            raise ValidationError(
                f"Cannot transition CDD plate import from '{self.status}' to '{target}'"
            )

    def start_discovery(self) -> None:
        """PENDING -> DISCOVERING."""
        self._guard_transition(CddPlateImportStatus.DISCOVERING)
        self.status = CddPlateImportStatus.DISCOVERING
        self.updated_at = datetime.now(UTC)

    def complete_discovery(self, total_count: int) -> None:
        """DISCOVERING -> PROCESSING. Sets total_count."""
        self._guard_transition(CddPlateImportStatus.PROCESSING)
        if total_count < 0:
            raise ValidationError("total_count must not be negative")
        self.status = CddPlateImportStatus.PROCESSING
        self.total_count = total_count
        self.updated_at = datetime.now(UTC)
        self.register_event(
            CddPlateImportDiscoveryComplete(
                aggregate_id=self.id,
                aggregate_type="CddPlateImport",
                total_count=total_count,
            )
        )

    def record_registered(self, count: int = 1) -> None:
        self._guard_processing()
        self.plates_registered += count
        self.updated_at = datetime.now(UTC)

    def record_duplicate(self, count: int = 1) -> None:
        self._guard_processing()
        self.plates_duplicate += count
        self.updated_at = datetime.now(UTC)

    def record_error(self, count: int = 1) -> None:
        self._guard_processing()
        self.plates_error += count
        self.updated_at = datetime.now(UTC)

    def record_wells(self, mapped: int = 0, unresolved: int = 0) -> None:
        self._guard_processing()
        self.wells_mapped += mapped
        self.wells_unresolved += unresolved
        self.updated_at = datetime.now(UTC)

    def update_offset(self, offset: int) -> None:
        self._guard_processing()
        self.last_processed_offset = offset
        self.updated_at = datetime.now(UTC)

    def complete(self) -> None:
        """PROCESSING -> COMPLETED or COMPLETED_WITH_ERRORS."""
        if self.total_count > 0 and self.processed_count > self.total_count:
            self.total_count = self.processed_count
        target = (
            CddPlateImportStatus.COMPLETED_WITH_ERRORS
            if self.plates_error > 0
            else CddPlateImportStatus.COMPLETED
        )
        self._guard_transition(target)
        self.status = target
        self.completed_at = datetime.now(UTC)
        self.updated_at = datetime.now(UTC)
        self.register_event(
            CddPlateImportCompleted(
                aggregate_id=self.id,
                aggregate_type="CddPlateImport",
                plates_registered=self.plates_registered,
                plates_duplicate=self.plates_duplicate,
                plates_error=self.plates_error,
                wells_mapped=self.wells_mapped,
                wells_unresolved=self.wells_unresolved,
            )
        )

    def fail(self, reason: str) -> None:
        """DISCOVERING or PROCESSING -> FAILED."""
        self._guard_transition(CddPlateImportStatus.FAILED)
        self.status = CddPlateImportStatus.FAILED
        self.completed_at = datetime.now(UTC)
        self.updated_at = datetime.now(UTC)
        self.register_event(
            CddPlateImportFailed(
                aggregate_id=self.id,
                aggregate_type="CddPlateImport",
                reason=reason,
            )
        )

    def _guard_processing(self) -> None:
        if self.status != CddPlateImportStatus.PROCESSING:
            raise ValidationError(
                "Can only record results while CDD plate import is processing"
            )
