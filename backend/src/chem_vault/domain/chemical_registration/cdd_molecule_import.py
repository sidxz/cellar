"""CddMoleculeImport aggregate root — tracks import of molecules from a CDD Vault."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from chem_vault.domain.chemical_registration.enums import (
    CddImportMode,
    CddMoleculeImportStatus,
)
from chem_vault.domain.chemical_registration.events import (
    CddMoleculeImportCompleted,
    CddMoleculeImportDiscoveryComplete,
    CddMoleculeImportFailed,
    CddMoleculeImportStarted,
)
from chem_vault.domain.shared.entity import AggregateRoot
from chem_vault.domain.shared.errors import ValidationError

# ---------------------------------------------------------------------------
# State-machine transition table
# ---------------------------------------------------------------------------

_TRANSITIONS: dict[CddMoleculeImportStatus, set[CddMoleculeImportStatus]] = {
    CddMoleculeImportStatus.PENDING: {CddMoleculeImportStatus.DISCOVERING},
    CddMoleculeImportStatus.DISCOVERING: {
        CddMoleculeImportStatus.PROCESSING,
        CddMoleculeImportStatus.FAILED,
    },
    CddMoleculeImportStatus.PROCESSING: {
        CddMoleculeImportStatus.COMPLETED,
        CddMoleculeImportStatus.COMPLETED_WITH_ERRORS,
        CddMoleculeImportStatus.FAILED,
    },
    CddMoleculeImportStatus.COMPLETED: set(),
    CddMoleculeImportStatus.COMPLETED_WITH_ERRORS: set(),
    CddMoleculeImportStatus.FAILED: set(),
}


class CddMoleculeImport(AggregateRoot):
    """Import operation that pulls molecules + batches from an external CDD Vault.

    State machine::

        pending -> discovering -> processing -> completed
                                             -> completed_with_errors
                   discovering -> failed  (auth error, vault not found)
                                 processing -> failed  (unrecoverable)

    Invariants:
        - cdd_vault_id must not be empty
        - total_count is set after discovery
        - When completed: total_count = registered + duplicate + error + skipped
    """

    def __init__(
        self,
        *,
        id: uuid.UUID | None = None,
        workspace_id: uuid.UUID,
        cdd_vault_id: str,
        import_mode: CddImportMode,
        originating_org_id: uuid.UUID,
        filter_criteria: dict | None = None,
        status: CddMoleculeImportStatus = CddMoleculeImportStatus.PENDING,
        workflow_id: str | None = None,
        total_count: int = 0,
        registered_count: int = 0,
        duplicate_count: int = 0,
        error_count: int = 0,
        skipped_count: int = 0,
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
        self.import_mode = import_mode
        self.originating_org_id = originating_org_id
        self.filter_criteria = filter_criteria
        self.status = status
        self.workflow_id = workflow_id
        self.total_count = total_count
        self.registered_count = registered_count
        self.duplicate_count = duplicate_count
        self.error_count = error_count
        self.skipped_count = skipped_count
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
        import_mode: CddImportMode,
        originating_org_id: uuid.UUID,
        submitted_by: uuid.UUID,
        workflow_id: str | None = None,
        filter_criteria: dict | None = None,
    ) -> CddMoleculeImport:
        """Create a new import in PENDING status."""
        imp = cls(
            workspace_id=workspace_id,
            cdd_vault_id=cdd_vault_id,
            import_mode=import_mode,
            originating_org_id=originating_org_id,
            submitted_by=submitted_by,
            workflow_id=workflow_id,
            filter_criteria=filter_criteria,
        )
        imp.register_event(
            CddMoleculeImportStarted(
                aggregate_id=imp.id,
                aggregate_type="CddMoleculeImport",
                workspace_id=workspace_id,
                cdd_vault_id=cdd_vault_id,
                import_mode=import_mode.value,
                submitted_by=submitted_by,
            )
        )
        return imp

    # ------------------------------------------------------------------
    # Computed property
    # ------------------------------------------------------------------

    @property
    def processed_count(self) -> int:
        return self.registered_count + self.duplicate_count + self.error_count + self.skipped_count

    # ------------------------------------------------------------------
    # State transitions
    # ------------------------------------------------------------------

    def _guard_transition(self, target: CddMoleculeImportStatus) -> None:
        allowed = _TRANSITIONS.get(self.status, set())
        if target not in allowed:
            raise ValidationError(
                f"Cannot transition CDD import from '{self.status}' to '{target}'"
            )

    def start_discovery(self) -> None:
        """PENDING -> DISCOVERING."""
        self._guard_transition(CddMoleculeImportStatus.DISCOVERING)
        self.status = CddMoleculeImportStatus.DISCOVERING
        self.updated_at = datetime.now(UTC)

    def complete_discovery(self, total_count: int) -> None:
        """DISCOVERING -> PROCESSING. Sets total_count."""
        self._guard_transition(CddMoleculeImportStatus.PROCESSING)
        if total_count < 0:
            raise ValidationError("total_count must not be negative")
        self.status = CddMoleculeImportStatus.PROCESSING
        self.total_count = total_count
        self.updated_at = datetime.now(UTC)
        self.register_event(
            CddMoleculeImportDiscoveryComplete(
                aggregate_id=self.id,
                aggregate_type="CddMoleculeImport",
                workspace_id=self.workspace_id,
                total_count=total_count,
            )
        )

    def record_registered(self, count: int = 1) -> None:
        """Increment registered_count (must be PROCESSING)."""
        self._guard_processing()
        self.registered_count += count
        self.updated_at = datetime.now(UTC)

    def record_duplicate(self, count: int = 1) -> None:
        """Increment duplicate_count (must be PROCESSING)."""
        self._guard_processing()
        self.duplicate_count += count
        self.updated_at = datetime.now(UTC)

    def record_error(self, count: int = 1) -> None:
        """Increment error_count (must be PROCESSING)."""
        self._guard_processing()
        self.error_count += count
        self.updated_at = datetime.now(UTC)

    def record_skipped(self, count: int = 1) -> None:
        """Increment skipped_count (must be PROCESSING)."""
        self._guard_processing()
        self.skipped_count += count
        self.updated_at = datetime.now(UTC)

    def update_offset(self, offset: int) -> None:
        """Update the pagination cursor for crash recovery."""
        self._guard_processing()
        self.last_processed_offset = offset
        self.updated_at = datetime.now(UTC)

    def complete(self) -> None:
        """PROCESSING -> COMPLETED or COMPLETED_WITH_ERRORS.

        Uses >= rather than == because CDD's molecule count API can return
        a stale cached value that differs slightly from the actual export.
        """
        if self.total_count > 0 and self.processed_count > self.total_count:
            # Update total_count to actual processed so the record is consistent
            self.total_count = self.processed_count
        target = (
            CddMoleculeImportStatus.COMPLETED_WITH_ERRORS
            if self.error_count > 0
            else CddMoleculeImportStatus.COMPLETED
        )
        self._guard_transition(target)
        self.status = target
        self.completed_at = datetime.now(UTC)
        self.updated_at = datetime.now(UTC)
        self.register_event(
            CddMoleculeImportCompleted(
                aggregate_id=self.id,
                aggregate_type="CddMoleculeImport",
                workspace_id=self.workspace_id,
                registered_count=self.registered_count,
                duplicate_count=self.duplicate_count,
                error_count=self.error_count,
                skipped_count=self.skipped_count,
            )
        )

    def fail(self, reason: str) -> None:
        """DISCOVERING or PROCESSING -> FAILED."""
        self._guard_transition(CddMoleculeImportStatus.FAILED)
        self.status = CddMoleculeImportStatus.FAILED
        self.completed_at = datetime.now(UTC)
        self.updated_at = datetime.now(UTC)
        self.register_event(
            CddMoleculeImportFailed(
                aggregate_id=self.id,
                aggregate_type="CddMoleculeImport",
                workspace_id=self.workspace_id,
                reason=reason,
            )
        )

    def _guard_processing(self) -> None:
        if self.status != CddMoleculeImportStatus.PROCESSING:
            raise ValidationError(
                "Can only record results while CDD import is processing"
            )
