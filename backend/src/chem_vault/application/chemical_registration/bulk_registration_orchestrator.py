"""Protocol + DTOs for dispatching bulk molecule registration workflows."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True, kw_only=True)
class StartBulkRegistrationRequest:
    """Engine-agnostic input for starting a bulk registration workflow.

    The orchestrator is responsible for persisting the upload payload to a
    location its workers can read; ``content`` is passed by value because
    callers don't know what storage layer the engine uses.
    """

    workspace_id: uuid.UUID
    originating_org_id: uuid.UUID
    submitted_by: uuid.UUID
    filename: str
    file_format: str
    content: bytes


@dataclass(frozen=True, kw_only=True)
class BulkRegistrationProgress:
    """Engine-agnostic progress snapshot of a bulk registration workflow."""

    bulk_reg_id: str
    status: str
    total_count: int
    registered_count: int
    duplicate_count: int
    error_count: int
    disclosed_count: int
    merge_candidate_count: int
    conflict_count: int
    merge_candidates: list[dict] = field(default_factory=list)
    chunks_processed: int
    chunks_total: int


class BulkRegistrationOrchestrator(Protocol):
    """Dispatches and inspects bulk registration workflows."""

    async def start(self, request: StartBulkRegistrationRequest) -> str:
        """Start a workflow; return its workflow_id.

        Raises ``WorkflowOrchestratorUnavailable`` if the engine is down —
        callers may catch this and fall back to a synchronous in-process
        registration path.
        """
        ...

    async def get_progress(self, workflow_id: str) -> BulkRegistrationProgress:
        """Return the current progress snapshot.

        Raises ``NotFoundError`` if the workflow is not in the runtime.
        Raises ``WorkflowOrchestratorUnavailable`` if the engine is down.
        """
        ...
