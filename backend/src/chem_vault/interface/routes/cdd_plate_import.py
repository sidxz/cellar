"""CDD plate import API routes."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import async_sessionmaker
from temporalio.client import WorkflowExecutionStatus
from temporalio.service import RPCError, RPCStatusCode

from chem_vault.application.auth import require_editor
from chem_vault.application.cdd_import.start_cdd_plate_import import (
    StartCddPlateImportCommand,
)
from chem_vault.infrastructure.persistence.sqlalchemy.inventory.cdd_plate_import_repository import (
    SQLAlchemyCddPlateImportRepository,
)
from chem_vault.infrastructure.persistence.unit_of_work import AsyncUnitOfWork
from chem_vault.infrastructure.temporal.task_queues import MAIN_TASK_QUEUE
from chem_vault.infrastructure.temporal.workflows.cdd_plate_import import (
    CddPlateImportWorkflow,
    CddPlateImportWorkflowInput,
)
from chem_vault.interface.dependencies import (
    AuthDep,
    ForceFailCddPlateImportDep,
    ListCddPlateImportsDep,
    StartCddPlateImportDep,
)
from chem_vault.interface.error_handlers import result_to_response

router = APIRouter(prefix="/api/v1/cdd-import/plates", tags=["cdd-plate-import"])


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------


class CddPlateImportAcceptedResponse(BaseModel):
    import_id: str | None = None
    workflow_id: str
    status: str = "pending"


class CddPlateImportStatusResponse(BaseModel):
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


class CddPlateImportSummary(BaseModel):
    id: str
    cdd_vault_id: str
    status: str
    workflow_id: str | None
    total_count: int
    plates_registered: int
    plates_duplicate: int
    plates_error: int
    wells_mapped: int
    wells_unresolved: int
    submitted_at: str
    completed_at: str | None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_temporal_client(request: Request):
    client = getattr(request.app.state, "temporal_client", None)
    if client is None:
        raise HTTPException(
            status_code=503,
            detail="Temporal is not available. Plate import requires Temporal.",
        )
    return client


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("", response_model=list[CddPlateImportSummary])
async def list_cdd_plate_imports(
    auth: AuthDep,
    use_case: ListCddPlateImportsDep,
) -> list[CddPlateImportSummary]:
    from chem_vault.application.cdd_import.list_cdd_plate_imports import (
        ListCddPlateImportsQuery,
    )

    result = await use_case(
        ListCddPlateImportsQuery(workspace_id=auth.workspace_id),
        auth=auth,
    )
    imports = result_to_response(result)
    return [
        CddPlateImportSummary(
            id=str(imp.id),
            cdd_vault_id=imp.cdd_vault_id,
            status=imp.status.value,
            workflow_id=imp.workflow_id,
            total_count=imp.total_count,
            plates_registered=imp.plates_registered,
            plates_duplicate=imp.plates_duplicate,
            plates_error=imp.plates_error,
            wells_mapped=imp.wells_mapped,
            wells_unresolved=imp.wells_unresolved,
            submitted_at=imp.submitted_at.isoformat(),
            completed_at=imp.completed_at.isoformat() if imp.completed_at else None,
        )
        for imp in imports
    ]


@router.post("", response_model=CddPlateImportAcceptedResponse, status_code=202)
async def start_cdd_plate_import(
    request: Request,
    auth: AuthDep,
    use_case: StartCddPlateImportDep,
) -> CddPlateImportAcceptedResponse:
    temporal_client = _get_temporal_client(request)

    cmd = StartCddPlateImportCommand(workspace_id=auth.workspace_id)
    result = await use_case(cmd, auth=auth)
    config = result_to_response(result)

    workflow_id = f"cdd-plate-import-{auth.workspace_id}-{uuid.uuid4()}"
    await temporal_client.start_workflow(
        CddPlateImportWorkflow.run,
        CddPlateImportWorkflowInput(
            workspace_id=str(auth.workspace_id),
            cdd_vault_id=config.vault_id,
            submitted_by=str(auth.user_id),
            secret_ref=config.secret_ref,
            entity_mappings=config.entity_mappings,
        ),
        id=workflow_id,
        task_queue=MAIN_TASK_QUEUE,
    )

    return CddPlateImportAcceptedResponse(workflow_id=workflow_id, status="pending")


@router.get("/{workflow_id}/status", response_model=CddPlateImportStatusResponse)
async def get_cdd_plate_import_status(
    request: Request,
    auth: AuthDep,
    workflow_id: str,
) -> CddPlateImportStatusResponse:
    temporal_client = _get_temporal_client(request)
    _verify_workspace_prefix(workflow_id, auth.workspace_id)

    try:
        handle = temporal_client.get_workflow_handle(workflow_id)
        progress = await handle.query(CddPlateImportWorkflow.get_progress)
        status = progress.status

        if status not in ("completed", "completed_with_errors", "failed"):
            try:
                desc = await handle.describe()
                if desc.status in (
                    WorkflowExecutionStatus.FAILED,
                    WorkflowExecutionStatus.TERMINATED,
                    WorkflowExecutionStatus.TIMED_OUT,
                    WorkflowExecutionStatus.CANCELED,
                ):
                    status = "failed"
                    await _sync_failed_import_to_db(
                        request, auth.workspace_id, progress.import_id
                    )
            except Exception:
                pass

        return CddPlateImportStatusResponse(
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
    except RPCError as exc:
        if exc.status == RPCStatusCode.NOT_FOUND:
            raise HTTPException(status_code=404, detail=f"Workflow not found: {workflow_id}") from exc
    except Exception:
        pass

    # Fallback: DB
    container = request.app.state.container
    session_factory = container[async_sessionmaker]
    uow = AsyncUnitOfWork(session_factory)
    repo = SQLAlchemyCddPlateImportRepository(uow)
    async with uow:
        imp = await repo.find_by_workflow_id_in_workspace(auth.workspace_id, workflow_id)
    if imp is None:
        raise HTTPException(status_code=404, detail=f"Import not found: {workflow_id}")
    return CddPlateImportStatusResponse(
        import_id=str(imp.id),
        status=imp.status.value,
        total_count=imp.total_count,
        plates_registered=imp.plates_registered,
        plates_duplicate=imp.plates_duplicate,
        plates_error=imp.plates_error,
        wells_mapped=imp.wells_mapped,
        wells_unresolved=imp.wells_unresolved,
        current_offset=imp.last_processed_offset,
        pages_processed=0,
    )


@router.post("/{workflow_id}/cancel", status_code=204)
async def cancel_cdd_plate_import(
    request: Request,
    auth: AuthDep,
    workflow_id: str,
) -> None:
    require_editor(auth)
    temporal_client = _get_temporal_client(request)
    _verify_workspace_prefix(workflow_id, auth.workspace_id)

    try:
        handle = temporal_client.get_workflow_handle(workflow_id)
        await handle.signal(CddPlateImportWorkflow.cancel)
    except RPCError as exc:
        if exc.status == RPCStatusCode.NOT_FOUND:
            return
        raise


@router.post("/{import_id}/force-fail", status_code=204)
async def force_fail_cdd_plate_import(
    auth: AuthDep,
    use_case: ForceFailCddPlateImportDep,
    import_id: str,
) -> None:
    from chem_vault.application.cdd_import.force_fail_cdd_plate_import import (
        ForceFailCddPlateImportCommand,
    )

    result = await use_case(
        ForceFailCddPlateImportCommand(
            workspace_id=auth.workspace_id,
            import_id=uuid.UUID(import_id),
        ),
        auth=auth,
    )
    result_to_response(result)


def _verify_workspace_prefix(workflow_id: str, workspace_id: uuid.UUID) -> None:
    prefix = "cdd-plate-import-"
    if not workflow_id.startswith(prefix):
        raise HTTPException(status_code=404, detail="Invalid workflow ID format")
    remainder = workflow_id[len(prefix):]
    if len(remainder) < 37:
        raise HTTPException(status_code=404, detail="Invalid workflow ID format")
    embedded_ws = remainder[:36]
    if embedded_ws != str(workspace_id):
        raise HTTPException(status_code=404, detail=f"Workflow not found: {workflow_id}")


async def _sync_failed_import_to_db(
    request: Request, workspace_id: uuid.UUID, import_id: str
) -> None:
    if not import_id:
        return
    try:
        container = request.app.state.container
        session_factory = container[async_sessionmaker]
        uow = AsyncUnitOfWork(session_factory)
        repo = SQLAlchemyCddPlateImportRepository(uow)
        async with uow:
            imp = await repo.find_by_id_in_workspace(
                workspace_id, uuid.UUID(import_id)
            )
            if imp is None:
                return
            if imp.status.value in ("completed", "completed_with_errors", "failed"):
                return
            imp.fail("Workflow crashed (detected by status poll)")
            await repo.save(imp)
            await uow.commit()
    except Exception:
        pass
