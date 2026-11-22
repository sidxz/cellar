"""Protocol + DTOs for dispatching CDD molecule import workflows.

The route does not know whether the underlying engine is Temporal, Celery,
or in-process — it talks only to ``CddMoleculeImportOrchestrator``.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, kw_only=True)
class StartCddMoleculeImportRequest:
    """Engine-agnostic input for starting a CDD molecule import workflow."""

    workspace_id: uuid.UUID
    cdd_vault_id: str
    import_mode: str
    submitted_by: uuid.UUID
    originating_org_id: uuid.UUID
    secret_ref: str
    entity_mappings: list[dict]
    registration_mapping: list[dict] | None = None  # vault field → target, see data source
    filter_criteria: dict | None = None
    max_molecules: int | None = None
    create_batch_on_duplicate: bool | None = None
    # The starter's Duar org (their token) and the discloser pick (None = them).
    submitted_by_org_id: uuid.UUID | None = None
    disclosed_by: uuid.UUID | None = None
    disclosed_by_org_id: uuid.UUID | None = None


@dataclass(frozen=True, kw_only=True)
class ResumeCddMoleculeImportRequest:
    """Start a failed import again from where it stopped, on the export it saved."""

    workspace_id: uuid.UUID
    import_id: uuid.UUID
    cdd_vault_id: str
    import_mode: str
    submitted_by: uuid.UUID  # who resumed it: the actor of what the run registers now
    originating_org_id: uuid.UUID
    filter_criteria: dict | None
    run_settings: dict  # the options the run started with
    cdd_export_id: int
    resume_offset: int
    total_count: int
    registered_count: int
    duplicate_count: int
    error_count: int
    skipped_count: int
    # The resumer's Duar org (their token) and the discloser pick (stored on the import).
    submitted_by_org_id: uuid.UUID | None = None
    disclosed_by: uuid.UUID | None = None
    disclosed_by_org_id: uuid.UUID | None = None


@dataclass(frozen=True, kw_only=True)
class CddMoleculeImportProgress:
    """Engine-agnostic progress snapshot of a CDD molecule import workflow.

    ``status`` is one of the workflow's own state strings (``"pending"``,
    ``"processing"``, ``"discovering"``, ``"exporting"``, ``"completed"``,
    ``"completed_with_errors"``, ``"failed"``). The adapter reconciles
    engine-level crashes (terminal-but-not-completed) into ``"failed"``
    before returning.
    """

    import_id: str
    status: str
    total_count: int
    registered_count: int
    duplicate_count: int
    error_count: int
    skipped_count: int
    current_offset: int
    pages_processed: int


class CddMoleculeImportOrchestrator(Protocol):
    """Dispatches and inspects CDD molecule import workflows."""

    async def start(self, request: StartCddMoleculeImportRequest) -> str:
        """Start a workflow; return its workflow_id.

        Raises ``WorkflowOrchestratorUnavailable`` if the engine is down.
        """
        ...

    async def resume(self, request: ResumeCddMoleculeImportRequest) -> str:
        """Start the import's run again from ``resume_offset``; return the new workflow_id.

        Raises ``ValidationError`` if the export is no longer on disk, ``ConflictError``
        if this resume is already running, ``WorkflowOrchestratorUnavailable`` if the
        engine is down.
        """
        ...

    async def get_progress(self, workflow_id: str) -> CddMoleculeImportProgress:
        """Return the current progress snapshot.

        Raises ``NotFoundError`` if no workflow with that id is known to the
        runtime (caller may then fall back to a DB read).
        Raises ``WorkflowOrchestratorUnavailable`` if the engine is down.
        """
        ...

    async def terminate(self, workflow_id: str, reason: str) -> None:
        """Stop the workflow at once: nothing more runs in it, no clean-up either.

        No-op if it has already ended or is not known. Raises
        ``WorkflowOrchestratorUnavailable`` if the engine is down.
        """
        ...

    async def cancel(self, workflow_id: str) -> None:
        """Send a cancel signal to the workflow.

        No-op (returns silently) if the workflow is already terminal or not
        found — the caller's intent ("make it stop") is satisfied either way.
        Raises ``WorkflowOrchestratorUnavailable`` if the engine is down.
        """
        ...
