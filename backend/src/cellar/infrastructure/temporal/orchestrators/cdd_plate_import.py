"""Temporal adapter for the ``CddPlateImportOrchestrator`` Protocol."""

from __future__ import annotations

import logging
import uuid

from temporalio.client import Client, WorkflowExecutionStatus
from temporalio.service import RPCError, RPCStatusCode

from cellar.application.cdd_import.cdd_plate_import_orchestrator import (
    CddPlateImportProgress,
    StartCddPlateImportRequest,
)
from cellar.application.orchestration.workflow_status import (
    WorkflowOrchestratorUnavailable,
)
from cellar.domain.shared.errors import NotFoundError
from cellar.infrastructure.temporal.task_queues import MAIN_TASK_QUEUE
from cellar.infrastructure.temporal.workflows.cdd_plate_import import (
    CddPlateImportWorkflow,
    CddPlateImportWorkflowInput,
)

logger = logging.getLogger(__name__)

_TERMINAL_FAILURE_STATUSES = (
    WorkflowExecutionStatus.FAILED,
    WorkflowExecutionStatus.TERMINATED,
    WorkflowExecutionStatus.TIMED_OUT,
    WorkflowExecutionStatus.CANCELED,
)


class TemporalCddPlateImportOrchestrator:
    """Implements ``CddPlateImportOrchestrator`` against a Temporal client."""

    def __init__(self, client: Client) -> None:
        self._client = client

    async def start(self, request: StartCddPlateImportRequest) -> str:
        workflow_id = f"cdd-plate-import-{request.workspace_id}-{uuid.uuid4()}"
        await self._client.start_workflow(
            CddPlateImportWorkflow.run,
            CddPlateImportWorkflowInput(
                workspace_id=str(request.workspace_id),
                cdd_vault_id=request.cdd_vault_id,
                submitted_by=str(request.submitted_by),
                secret_ref=request.secret_ref,
                entity_mappings=request.entity_mappings,
            ),
            id=workflow_id,
            task_queue=MAIN_TASK_QUEUE,
        )
        return workflow_id

    async def get_progress(self, workflow_id: str) -> CddPlateImportProgress:
        handle = self._client.get_workflow_handle(workflow_id)
        try:
            progress = await handle.query(CddPlateImportWorkflow.get_progress)
        except RPCError as exc:
            if exc.status == RPCStatusCode.NOT_FOUND:
                raise NotFoundError("Workflow", workflow_id) from exc
            raise

        status = progress.status
        if status not in ("completed", "completed_with_errors", "failed"):
            try:
                desc = await handle.describe()
                if desc.status in _TERMINAL_FAILURE_STATUSES:
                    status = "failed"
            except Exception:
                logger.warning(
                    "temporal_describe_failed: workflow_id=%s",
                    workflow_id,
                )

        return CddPlateImportProgress(
            import_id=progress.import_id,
            status=status,
            total_count=progress.total_count,
            plates_registered=progress.plates_registered,
            plates_duplicate=progress.plates_duplicate,
            plates_error=progress.plates_error,
            wells_mapped=progress.wells_mapped,
            wells_unresolved=progress.wells_unresolved,
            current_offset=progress.current_offset,
            pages_processed=progress.pages_processed,
        )

    async def cancel(self, workflow_id: str) -> None:
        handle = self._client.get_workflow_handle(workflow_id)
        try:
            await handle.signal(CddPlateImportWorkflow.cancel)
        except RPCError as exc:
            if exc.status == RPCStatusCode.NOT_FOUND:
                return
            raise


class NullCddPlateImportOrchestrator:
    async def start(self, request: StartCddPlateImportRequest) -> str:
        raise WorkflowOrchestratorUnavailable(
            "Temporal is not available. Plate import requires Temporal."
        )

    async def get_progress(self, workflow_id: str) -> CddPlateImportProgress:
        raise WorkflowOrchestratorUnavailable(
            "Temporal is not available. Cannot query workflow progress."
        )

    async def cancel(self, workflow_id: str) -> None:
        raise WorkflowOrchestratorUnavailable("Temporal is not available. Cannot cancel workflow.")
