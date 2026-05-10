"""Temporal adapter for the ``BulkRegistrationOrchestrator`` Protocol.

Persists the upload to the worker-readable storage location, then dispatches
``BulkRegistrationWorkflow``. ``get_progress`` translates the workflow's
internal progress dataclass into the application DTO.
"""

from __future__ import annotations

import uuid

from temporalio.client import Client
from temporalio.service import RPCError, RPCStatusCode

from chem_vault.application.chemical_registration.bulk_registration_orchestrator import (
    BulkRegistrationProgress,
    StartBulkRegistrationRequest,
)
from chem_vault.application.orchestration.workflow_status import (
    WorkflowOrchestratorUnavailable,
)
from chem_vault.domain.shared.errors import NotFoundError
from chem_vault.infrastructure.temporal.activities.file_parsing import save_upload_to_storage
from chem_vault.infrastructure.temporal.task_queues import MAIN_TASK_QUEUE
from chem_vault.infrastructure.temporal.workflows.bulk_registration import (
    BulkRegistrationWorkflow,
    BulkRegistrationWorkflowInput,
)


class TemporalBulkRegistrationOrchestrator:
    """Implements ``BulkRegistrationOrchestrator`` against a Temporal client."""

    def __init__(self, client: Client) -> None:
        self._client = client

    async def start(self, request: StartBulkRegistrationRequest) -> str:
        storage_path = save_upload_to_storage(request.content, request.filename)
        workflow_id = f"bulk-reg-{request.workspace_id}-{uuid.uuid4()}"

        await self._client.start_workflow(
            BulkRegistrationWorkflow.run,
            BulkRegistrationWorkflowInput(
                workspace_id=str(request.workspace_id),
                originating_org_id=str(request.originating_org_id),
                submitted_by=str(request.submitted_by),
                source_file=request.filename,
                file_format=request.file_format,
                storage_path=storage_path,
                filename=request.filename,
                create_batch_on_duplicate=request.create_batch_on_duplicate,
            ),
            id=workflow_id,
            task_queue=MAIN_TASK_QUEUE,
        )
        return workflow_id

    async def get_progress(self, workflow_id: str) -> BulkRegistrationProgress:
        handle = self._client.get_workflow_handle(workflow_id)
        try:
            progress = await handle.query(BulkRegistrationWorkflow.get_progress)
        except RPCError as exc:
            if exc.status == RPCStatusCode.NOT_FOUND:
                raise NotFoundError("Workflow", workflow_id) from exc
            raise
        except Exception as exc:
            # Bulk registration's existing behavior: any query failure → 404.
            raise NotFoundError("Workflow", workflow_id) from exc

        return BulkRegistrationProgress(
            bulk_reg_id=progress.bulk_reg_id,
            status=progress.status,
            total_count=progress.total_count,
            registered_count=progress.registered_count,
            duplicate_count=progress.duplicate_count,
            error_count=progress.error_count,
            disclosed_count=progress.disclosed_count,
            merge_candidate_count=progress.merge_candidate_count,
            conflict_count=progress.conflict_count,
            merge_candidates=list(progress.merge_candidates),
            chunks_processed=progress.chunks_processed,
            chunks_total=progress.chunks_total,
        )


class NullBulkRegistrationOrchestrator:
    """Stand-in when Temporal is unavailable.

    The start use case catches ``WorkflowOrchestratorUnavailable`` and falls
    back to the in-process ``BulkRegistrationService``.
    """

    async def start(self, request: StartBulkRegistrationRequest) -> str:
        raise WorkflowOrchestratorUnavailable(
            "Temporal is not available — use the synchronous bulk registration path."
        )

    async def get_progress(self, workflow_id: str) -> BulkRegistrationProgress:
        raise WorkflowOrchestratorUnavailable("Temporal is not available.")
