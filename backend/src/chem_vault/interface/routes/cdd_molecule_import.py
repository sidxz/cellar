"""CDD molecule import API routes."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from temporalio.service import RPCError, RPCStatusCode

from chem_vault.application.auth import require_editor
from chem_vault.application.cdd_import.start_cdd_molecule_import import (
    StartCddMoleculeImportCommand,
)
from chem_vault.infrastructure.temporal.task_queues import MAIN_TASK_QUEUE
from chem_vault.infrastructure.temporal.workflows.cdd_vault_import import (
    CddVaultImportWorkflow,
    CddVaultImportWorkflowInput,
)
from chem_vault.interface.dependencies import AuthDep, StartCddMoleculeImportDep
from chem_vault.interface.error_handlers import result_to_response

router = APIRouter(prefix="/api/v1/cdd-import/molecules", tags=["cdd-molecule-import"])


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------


class StartCddMoleculeImportBody(BaseModel):
    originating_org_id: uuid.UUID
    import_mode: str = "full_vault"
    filter_criteria: dict | None = None
    max_molecules: int | None = None  # limit for testing; None = import all


class CddMoleculeImportAcceptedResponse(BaseModel):
    import_id: str | None = None
    workflow_id: str
    status: str = "pending"


class CddMoleculeImportStatusResponse(BaseModel):
    import_id: str
    status: str
    total_count: int
    registered_count: int
    duplicate_count: int
    error_count: int
    skipped_count: int
    current_offset: int
    pages_processed: int


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_temporal_client(request: Request):
    """Resolve the Temporal client or raise 503."""
    client = getattr(request.app.state, "temporal_client", None)
    if client is None:
        raise HTTPException(
            status_code=503,
            detail="Temporal is not available. Bulk CDD import requires Temporal.",
        )
    return client


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.post("", response_model=CddMoleculeImportAcceptedResponse, status_code=202)
async def start_cdd_molecule_import(
    request: Request,
    auth: AuthDep,
    use_case: StartCddMoleculeImportDep,
    body: StartCddMoleculeImportBody,
) -> CddMoleculeImportAcceptedResponse:
    """Start a CDD vault molecule import. Returns 202 with workflow_id."""
    temporal_client = _get_temporal_client(request)

    # Validate CDD config (use case enforces require_editor)
    cmd = StartCddMoleculeImportCommand(
        workspace_id=auth.workspace_id,
        import_mode=body.import_mode,
        filter_criteria=body.filter_criteria,
    )
    result = await use_case(cmd, auth=auth)
    config = result_to_response(result)

    # Start Temporal workflow — embed workspace_id for ownership checks
    workflow_id = f"cdd-mol-import-{auth.workspace_id}-{uuid.uuid4()}"
    await temporal_client.start_workflow(
        CddVaultImportWorkflow.run,
        CddVaultImportWorkflowInput(
            workspace_id=str(auth.workspace_id),
            cdd_vault_id=config.vault_id,
            import_mode=body.import_mode,
            submitted_by=str(auth.user_id),
            originating_org_id=str(body.originating_org_id),
            secret_ref=config.secret_ref,
            filter_criteria=body.filter_criteria,
            max_molecules=body.max_molecules,
        ),
        id=workflow_id,
        task_queue=MAIN_TASK_QUEUE,
    )

    return CddMoleculeImportAcceptedResponse(
        workflow_id=workflow_id,
        status="pending",
    )


@router.get("/{workflow_id}/status", response_model=CddMoleculeImportStatusResponse)
async def get_cdd_molecule_import_status(
    request: Request,
    auth: AuthDep,
    workflow_id: str,
) -> CddMoleculeImportStatusResponse:
    """Poll progress of a CDD molecule import workflow.

    Workspace-scoped: the workflow_id prefix contains the workspace_id,
    and the Temporal query is validated against the requesting workspace.
    """
    temporal_client = _get_temporal_client(request)

    # Verify workspace ownership via workflow_id convention
    _verify_workspace_prefix(workflow_id, auth.workspace_id)

    try:
        handle = temporal_client.get_workflow_handle(workflow_id)
        progress = await handle.query(CddVaultImportWorkflow.get_progress)
    except RPCError as exc:
        if exc.status == RPCStatusCode.NOT_FOUND:
            raise HTTPException(status_code=404, detail=f"Workflow not found: {workflow_id}") from exc
        raise

    return CddMoleculeImportStatusResponse(
        import_id=progress.import_id,
        status=progress.status,
        total_count=progress.total_count,
        registered_count=progress.registered_count,
        duplicate_count=progress.duplicate_count,
        error_count=progress.error_count,
        skipped_count=progress.skipped_count,
        current_offset=progress.current_offset,
        pages_processed=progress.pages_processed,
    )


@router.post("/{workflow_id}/cancel", status_code=204)
async def cancel_cdd_molecule_import(
    request: Request,
    auth: AuthDep,
    workflow_id: str,
) -> None:
    """Send a cancel signal to a running CDD molecule import workflow."""
    require_editor(auth)
    temporal_client = _get_temporal_client(request)
    _verify_workspace_prefix(workflow_id, auth.workspace_id)

    try:
        handle = temporal_client.get_workflow_handle(workflow_id)
        await handle.signal(CddVaultImportWorkflow.cancel)
    except RPCError as exc:
        if exc.status == RPCStatusCode.NOT_FOUND:
            raise HTTPException(status_code=404, detail=f"Workflow not found: {workflow_id}") from exc
        raise


def _verify_workspace_prefix(workflow_id: str, workspace_id: uuid.UUID) -> None:
    """Verify the workflow belongs to the requesting workspace.

    Workflow IDs have the format: ``cdd-mol-import-{workspace_id}-{uuid}``.
    We extract the embedded workspace_id and compare.
    """
    prefix = "cdd-mol-import-"
    if not workflow_id.startswith(prefix):
        raise HTTPException(status_code=404, detail="Invalid workflow ID format")
    remainder = workflow_id[len(prefix):]
    # remainder = "{workspace_uuid}-{random_uuid}"
    # workspace UUID is 36 chars
    if len(remainder) < 37:
        raise HTTPException(status_code=404, detail="Invalid workflow ID format")
    embedded_ws = remainder[:36]
    if embedded_ws != str(workspace_id):
        raise HTTPException(status_code=404, detail=f"Workflow not found: {workflow_id}")
