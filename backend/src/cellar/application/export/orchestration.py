"""ExportOrchestrator Protocol + DTO — implemented by Temporal and Null orchestrators (T13)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Protocol

# Re-export for symmetry with BulkRegistrationOrchestrator callers.
from cellar.application.orchestration.workflow_status import (
    WorkflowOrchestratorUnavailable,
)

__all__ = ["ExportOrchestrator", "StartExportWorkflowRequest", "WorkflowOrchestratorUnavailable"]


@dataclass(frozen=True, kw_only=True)
class StartExportWorkflowRequest:
    job_id: uuid.UUID
    workspace_id: uuid.UUID


class ExportOrchestrator(Protocol):
    async def start(self, request: StartExportWorkflowRequest) -> str: ...
    async def request_cancel(self, workflow_id: str) -> None: ...
