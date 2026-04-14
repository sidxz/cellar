"""CDD molecule import API routes."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import async_sessionmaker
from temporalio.client import WorkflowExecutionStatus
from temporalio.service import RPCError, RPCStatusCode

from chem_vault.application.auth import require_editor
from chem_vault.application.cdd_import.start_cdd_molecule_import import (
    StartCddMoleculeImportCommand,
)
from chem_vault.infrastructure.persistence.sqlalchemy.chemical_registration.cdd_molecule_import_repository import (
    SQLAlchemyCddMoleculeImportRepository,
)
from chem_vault.infrastructure.persistence.unit_of_work import AsyncUnitOfWork
from chem_vault.infrastructure.temporal.task_queues import MAIN_TASK_QUEUE
from chem_vault.infrastructure.temporal.workflows.cdd_vault_import import (
    CddVaultImportWorkflow,
    CddVaultImportWorkflowInput,
)
from chem_vault.interface.dependencies import (
    AuthDep,
    ForceFailCddMoleculeImportDep,
    ListCddMoleculeImportsDep,
    StartCddMoleculeImportDep,
)
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


class CddMoleculeImportSummary(BaseModel):
    id: str
    cdd_vault_id: str
    import_mode: str
    status: str
    workflow_id: str | None
    total_count: int
    registered_count: int
    duplicate_count: int
    error_count: int
    skipped_count: int
    submitted_at: str
    completed_at: str | None


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


@router.get("", response_model=list[CddMoleculeImportSummary])
async def list_cdd_molecule_imports(
    auth: AuthDep,
    use_case: ListCddMoleculeImportsDep,
) -> list[CddMoleculeImportSummary]:
    """List all CDD molecule imports for this workspace, newest first."""
    from chem_vault.application.cdd_import.list_cdd_molecule_imports import (
        ListCddMoleculeImportsQuery,
    )

    result = await use_case(
        ListCddMoleculeImportsQuery(workspace_id=auth.workspace_id),
        auth=auth,
    )
    imports = result_to_response(result)
    return [
        CddMoleculeImportSummary(
            id=str(imp.id),
            cdd_vault_id=imp.cdd_vault_id,
            import_mode=imp.import_mode.value,
            status=imp.status.value,
            workflow_id=imp.workflow_id,
            total_count=imp.total_count,
            registered_count=imp.registered_count,
            duplicate_count=imp.duplicate_count,
            error_count=imp.error_count,
            skipped_count=imp.skipped_count,
            submitted_at=imp.submitted_at.isoformat(),
            completed_at=imp.completed_at.isoformat() if imp.completed_at else None,
        )
        for imp in imports
    ]


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
        status = progress.status

        # Detect crashed workflows: Temporal says progress is non-terminal
        # but the execution actually failed/terminated (activity retries exhausted, etc.)
        if status not in ("completed", "completed_with_errors", "failed"):
            try:
                desc = await handle.describe()
                exec_status = desc.status
                if exec_status in (
                    WorkflowExecutionStatus.FAILED,
                    WorkflowExecutionStatus.TERMINATED,
                    WorkflowExecutionStatus.TIMED_OUT,
                    WorkflowExecutionStatus.CANCELED,
                ):
                    status = "failed"
                    # Sync DB aggregate to match — otherwise history
                    # still shows "processing" and the UI loops.
                    await _sync_failed_import_to_db(
                        request, auth.workspace_id, progress.import_id
                    )
            except Exception:
                pass  # describe() failed — use progress status as-is

        return CddMoleculeImportStatusResponse(
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
    except RPCError as exc:
        if exc.status == RPCStatusCode.NOT_FOUND:
            raise HTTPException(status_code=404, detail=f"Workflow not found: {workflow_id}") from exc
        # Fall through to DB lookup for nondeterminism errors, etc.
    except Exception:
        pass  # Fall through to DB lookup

    # Fallback: read from DB (handles completed/failed workflows and code-change replays)
    container = request.app.state.container
    session_factory = container[async_sessionmaker]
    uow = AsyncUnitOfWork(session_factory)
    repo = SQLAlchemyCddMoleculeImportRepository(uow)
    async with uow:
        imp = await repo.find_by_workflow_id_in_workspace(auth.workspace_id, workflow_id)
    if imp is None:
        raise HTTPException(status_code=404, detail=f"Import not found: {workflow_id}")
    return CddMoleculeImportStatusResponse(
        import_id=str(imp.id),
        status=imp.status.value,
        total_count=imp.total_count,
        registered_count=imp.registered_count,
        duplicate_count=imp.duplicate_count,
        error_count=imp.error_count,
        skipped_count=imp.skipped_count,
        current_offset=imp.last_processed_offset,
        pages_processed=0,
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
            # Workflow already terminated (crashed/completed) — that's fine,
            # the user wants it stopped and it already is. Return success.
            return
        raise


@router.post("/{import_id}/force-fail", status_code=204)
async def force_fail_cdd_molecule_import(
    auth: AuthDep,
    use_case: ForceFailCddMoleculeImportDep,
    import_id: str,
) -> None:
    """Force a stuck import to FAILED status. Admin action for cleanup."""
    from chem_vault.application.cdd_import.force_fail_cdd_molecule_import import (
        ForceFailCddMoleculeImportCommand,
    )

    result = await use_case(
        ForceFailCddMoleculeImportCommand(
            workspace_id=auth.workspace_id,
            import_id=uuid.UUID(import_id),
        ),
        auth=auth,
    )
    result_to_response(result)


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


async def _sync_failed_import_to_db(
    request: Request, workspace_id: uuid.UUID, import_id: str
) -> None:
    """Update a crashed import's DB record to FAILED.

    Called when the status endpoint detects the Temporal workflow is
    terminated but the DB aggregate is still in a non-terminal state.
    Best-effort — swallows errors so it never breaks the status response.
    """
    if not import_id:
        return
    try:
        container = request.app.state.container
        session_factory = container[async_sessionmaker]
        uow = AsyncUnitOfWork(session_factory)
        repo = SQLAlchemyCddMoleculeImportRepository(uow)
        async with uow:
            imp = await repo.find_by_id_in_workspace(
                workspace_id, uuid.UUID(import_id)
            )
            if imp is None:
                return
            if imp.status.value in ("completed", "completed_with_errors", "failed"):
                return  # Already terminal
            imp.fail("Workflow crashed (detected by status poll)")
            await repo.save(imp)
            await uow.commit()
    except Exception:
        pass  # Best-effort — don't break the status response
