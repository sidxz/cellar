"""Protocol + DTOs for dispatching CDD plate import workflows."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, kw_only=True)
class StartCddPlateImportRequest:
    """Engine-agnostic input for starting a CDD plate import workflow."""

    workspace_id: uuid.UUID
    cdd_vault_id: str
    submitted_by: uuid.UUID
    secret_ref: str
    entity_mappings: list[dict]


@dataclass(frozen=True, kw_only=True)
class CddPlateImportProgress:
    """Engine-agnostic progress snapshot of a CDD plate import workflow.

    ``status`` follows the same vocabulary as the workflow's own state
    machine; the adapter rewrites it to ``"failed"`` if Temporal reports
    the execution as terminal-but-not-completed.
    """

    import_id: str
    status: str
    total_count: int
    plates_registered: int
    plates_duplicate: int
    plates_error: int
    wells_mapped: int
    wells_unresolved: int
    current_offset: int
    pages_processed: int


class CddPlateImportOrchestrator(Protocol):
    """Dispatches and inspects CDD plate import workflows."""

    async def start(self, request: StartCddPlateImportRequest) -> str:
        """Start a workflow; return its workflow_id.

        Raises ``WorkflowOrchestratorUnavailable`` if the engine is down.
        """
        ...

    async def get_progress(self, workflow_id: str) -> CddPlateImportProgress:
        """Return the current progress snapshot.

        Raises ``NotFoundError`` if the workflow is not in the runtime.
        Raises ``WorkflowOrchestratorUnavailable`` if the engine is down.
        """
        ...

    async def cancel(self, workflow_id: str) -> None:
        """Send a cancel signal; no-op if already terminal or not found.

        Raises ``WorkflowOrchestratorUnavailable`` if the engine is down.
        """
        ...
