"""CddMoleculeImport aggregate root — tracks import of molecules from a CDD Vault."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from cellar.domain.chemical_registration.enums import (
    CddImportMode,
    CddMoleculeImportStatus,
)
from cellar.domain.chemical_registration.events import (
    CddMoleculeImportCompleted,
    CddMoleculeImportDiscoveryComplete,
    CddMoleculeImportFailed,
    CddMoleculeImportResumed,
    CddMoleculeImportStarted,
)
from cellar.domain.shared.entity import AggregateRoot
from cellar.domain.shared.errors import ValidationError

# ---------------------------------------------------------------------------
# State-machine transition table
# ---------------------------------------------------------------------------

REPORT_COUNTS = (
    "compounds_added",
    "compounds_matched",
    "batches_created",
    "batches_matched",
    "ids_added",
    "values_skipped",
    "problems",
)
MAX_PROBLEM_LINES = 500


def empty_report() -> dict:
    return {**dict.fromkeys(REPORT_COUNTS, 0), "problem_lines": []}


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
# Statuses an import never leaves (the run has finished).
TERMINAL_STATUSES = frozenset(s.value for s, after in _TRANSITIONS.items() if not after)


class CddMoleculeImport(AggregateRoot):
    """Import operation that pulls molecules + batches from an external CDD Vault.

    State machine::

        pending -> discovering -> processing -> completed
                                             -> completed_with_errors
                   discovering -> failed  (auth error, vault not found)
                                 processing -> failed  (unrecoverable)
                                       failed -> processing  (resume, see ``resume``)

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
        filter_criteria: dict | None = None,
        status: CddMoleculeImportStatus = CddMoleculeImportStatus.PENDING,
        workflow_id: str | None = None,
        total_count: int = 0,
        registered_count: int = 0,
        duplicate_count: int = 0,
        error_count: int = 0,
        skipped_count: int = 0,
        last_processed_offset: int = 0,
        report: dict | None = None,
        cdd_export_id: int | None = None,
        run_settings: dict | None = None,
        submitted_by: uuid.UUID,
        disclosed_by: uuid.UUID | None = None,
        disclosed_by_org_id: uuid.UUID | None = None,
        submitted_at: datetime | None = None,
        completed_at: datetime | None = None,
        failure_reason: str | None = None,
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
        self.filter_criteria = filter_criteria
        self.status = status
        self.workflow_id = workflow_id
        self.total_count = total_count
        self.registered_count = registered_count
        self.duplicate_count = duplicate_count
        self.error_count = error_count
        self.skipped_count = skipped_count
        self.last_processed_offset = last_processed_offset
        self.report = {**empty_report(), **(report or {})}
        # What a resume needs: the CDD export on disk, and the options the run started with.
        self.cdd_export_id = cdd_export_id
        self.run_settings = run_settings
        self.submitted_by = submitted_by
        # The discloser pick for every compound this import registers (None = the
        # person running it, and their Duar org). Kept so a resume uses it too.
        self.disclosed_by = disclosed_by
        self.disclosed_by_org_id = disclosed_by_org_id
        self.submitted_at = submitted_at or datetime.now(UTC)
        self.completed_at = completed_at
        self.failure_reason = failure_reason

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
        submitted_by: uuid.UUID,
        workflow_id: str | None = None,
        filter_criteria: dict | None = None,
        run_settings: dict | None = None,
        disclosed_by: uuid.UUID | None = None,
        disclosed_by_org_id: uuid.UUID | None = None,
    ) -> CddMoleculeImport:
        """Create a new import in PENDING status."""
        imp = cls(
            workspace_id=workspace_id,
            cdd_vault_id=cdd_vault_id,
            import_mode=import_mode,
            submitted_by=submitted_by,
            workflow_id=workflow_id,
            filter_criteria=filter_criteria,
            run_settings=run_settings,
            disclosed_by=disclosed_by,
            disclosed_by_org_id=disclosed_by_org_id,
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

    def complete_discovery(self, total_count: int, export_id: int | None = None) -> None:
        """DISCOVERING -> PROCESSING. Sets total_count, and the CDD export the run reads."""
        self._guard_transition(CddMoleculeImportStatus.PROCESSING)
        if total_count < 0:
            raise ValidationError("total_count must not be negative")
        self.status = CddMoleculeImportStatus.PROCESSING
        self.total_count = total_count
        if export_id is not None:
            self.cdd_export_id = export_id
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

    def record_report(self, delta: dict) -> None:
        """Add a chunk's report counts; keep its problem lines up to the cap."""
        self._guard_processing()
        for key in REPORT_COUNTS:
            self.report[key] += delta.get(key, 0)
        room = MAX_PROBLEM_LINES - len(self.report["problem_lines"])
        self.report["problem_lines"] = [
            *self.report["problem_lines"],
            *delta.get("problem_lines", [])[: max(room, 0)],
        ]
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
        self.failure_reason = reason
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

    @property
    def resumable(self) -> bool:
        """A failed run whose export and settings were saved can pick up where it stopped."""
        return (
            self.status == CddMoleculeImportStatus.FAILED
            and self.cdd_export_id is not None
            and self.run_settings is not None
        )

    def resume(self, workflow_id: str, resumed_by: uuid.UUID) -> None:
        """FAILED -> PROCESSING on a new workflow, from ``last_processed_offset``.

        Not in ``_TRANSITIONS``: failed stays a status the run has finished in until
        someone resumes it.
        """
        if not self.resumable:
            raise ValidationError("Only a failed import that saved its export can be resumed")
        self.status = CddMoleculeImportStatus.PROCESSING
        self.workflow_id = workflow_id
        self.completed_at = None
        self.failure_reason = None
        self.updated_at = datetime.now(UTC)
        self.register_event(
            CddMoleculeImportResumed(
                aggregate_id=self.id,
                aggregate_type="CddMoleculeImport",
                workspace_id=self.workspace_id,
                workflow_id=workflow_id,
                resumed_by=resumed_by,
                from_offset=self.last_processed_offset,
            )
        )

    def _guard_processing(self) -> None:
        if self.status != CddMoleculeImportStatus.PROCESSING:
            raise ValidationError("Can only record results while CDD import is processing")
