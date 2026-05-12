"""Temporal adapter for the ``CddMoleculeImportOrchestrator`` Protocol."""

from __future__ import annotations

import logging
import uuid

from temporalio.client import Client, WorkflowExecutionStatus
from temporalio.service import RPCError, RPCStatusCode

from cellar.application.cdd_import.cdd_molecule_import_orchestrator import (
    CddMoleculeImportProgress,
    StartCddMoleculeImportRequest,
)
from cellar.application.orchestration.workflow_status import (
    WorkflowOrchestratorUnavailable,
)
from cellar.domain.shared.errors import NotFoundError
from cellar.infrastructure.temporal.task_queues import MAIN_TASK_QUEUE
from cellar.infrastructure.temporal.workflows.cdd_vault_import import (
    CddVaultImportWorkflow,
    CddVaultImportWorkflowInput,
)

logger = logging.getLogger(__name__)

_TERMINAL_FAILURE_STATUSES = (
    WorkflowExecutionStatus.FAILED,
    WorkflowExecutionStatus.TERMINATED,
    WorkflowExecutionStatus.TIMED_OUT,
    WorkflowExecutionStatus.CANCELED,
)


class TemporalCddMoleculeImportOrchestrator:
    """Implements ``CddMoleculeImportOrchestrator`` against a Temporal client."""

    def __init__(self, client: Client) -> None:
        self._client = client

    async def start(self, request: StartCddMoleculeImportRequest) -> str:
        workflow_id = f"cdd-mol-import-{request.workspace_id}-{uuid.uuid4()}"
        await self._client.start_workflow(
            CddVaultImportWorkflow.run,
            CddVaultImportWorkflowInput(
                workspace_id=str(request.workspace_id),
                cdd_vault_id=request.cdd_vault_id,
                import_mode=request.import_mode,
                submitted_by=str(request.submitted_by),
                originating_org_id=str(request.originating_org_id),
                secret_ref=request.secret_ref,
                filter_criteria=request.filter_criteria,
                max_molecules=request.max_molecules,
                entity_mappings=request.entity_mappings,
                create_batch_on_duplicate=request.create_batch_on_duplicate,
            ),
            id=workflow_id,
            task_queue=MAIN_TASK_QUEUE,
        )
        return workflow_id

    async def get_progress(self, workflow_id: str) -> CddMoleculeImportProgress:
        handle = self._client.get_workflow_handle(workflow_id)
        try:
            progress = await handle.query(CddVaultImportWorkflow.get_progress)
        except RPCError as exc:
            if exc.status == RPCStatusCode.NOT_FOUND:
                raise NotFoundError("Workflow", workflow_id) from exc
            raise

        status = progress.status

        # Crash detection: if the workflow's own state machine still says
        # non-terminal but the runtime says the execution itself failed,
        # rewrite to "failed" so callers report the right thing.
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

        return CddMoleculeImportProgress(
            import_id=progress.import_id,
            status=status,
            total_count=progress.total_count,
            registered_count=progress.registered_count,
            duplicate_count=progress.duplicate_count,
            error_count=progress.error_count,
            skipped_count=progress.skipped_count,
            current_offset=progress.current_offset,
            pages_processed=progress.pages_processed,
        )

    async def cancel(self, workflow_id: str) -> None:
        handle = self._client.get_workflow_handle(workflow_id)
        try:
            await handle.signal(CddVaultImportWorkflow.cancel)
        except RPCError as exc:
            if exc.status == RPCStatusCode.NOT_FOUND:
                # Already terminal — caller's intent is satisfied.
                return
            raise


class NullCddMoleculeImportOrchestrator:
    """Stand-in used when the Temporal client is unavailable.

    Every method raises ``WorkflowOrchestratorUnavailable``. Use cases
    decide whether to surface that as a 503 or fall back to another path.
    """

    async def start(self, request: StartCddMoleculeImportRequest) -> str:
        raise WorkflowOrchestratorUnavailable(
            "Temporal is not available. Bulk CDD import requires Temporal."
        )

    async def get_progress(self, workflow_id: str) -> CddMoleculeImportProgress:
        raise WorkflowOrchestratorUnavailable(
            "Temporal is not available. Cannot query workflow progress."
        )

    async def cancel(self, workflow_id: str) -> None:
        raise WorkflowOrchestratorUnavailable("Temporal is not available. Cannot cancel workflow.")
