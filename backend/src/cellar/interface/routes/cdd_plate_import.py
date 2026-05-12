"""CDD plate import API routes."""

from __future__ import annotations

import uuid

from fastapi import APIRouter
from pydantic import BaseModel

from cellar.application.cdd_import.cancel_cdd_plate_import import (
    CancelCddPlateImportCommand,
)
from cellar.application.cdd_import.get_cdd_plate_import_runtime_status import (
    GetCddPlateImportRuntimeStatusQuery,
)
from cellar.application.cdd_import.start_cdd_plate_import import (
    StartCddPlateImportCommand,
)
from cellar.interface.dependencies import (
    AuthDep,
    CancelCddPlateImportDep,
    ForceFailCddPlateImportDep,
    GetCddPlateImportRuntimeStatusDep,
    ListCddPlateImportsDep,
    StartCddPlateImportDep,
)
from cellar.interface.error_handlers import result_to_response

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
# Routes
# ---------------------------------------------------------------------------


@router.get("", response_model=list[CddPlateImportSummary])
async def list_cdd_plate_imports(
    auth: AuthDep,
    use_case: ListCddPlateImportsDep,
) -> list[CddPlateImportSummary]:
    from cellar.application.cdd_import.list_cdd_plate_imports import (
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
    auth: AuthDep,
    use_case: StartCddPlateImportDep,
) -> CddPlateImportAcceptedResponse:
    cmd = StartCddPlateImportCommand(
        workspace_id=auth.workspace_id,
        submitted_by=auth.user_id,
    )
    result = await use_case(cmd, auth=auth)
    outcome = result_to_response(result)
    return CddPlateImportAcceptedResponse(workflow_id=outcome.workflow_id, status="pending")


@router.get("/{workflow_id}/status", response_model=CddPlateImportStatusResponse)
async def get_cdd_plate_import_status(
    auth: AuthDep,
    workflow_id: str,
    runtime_status_uc: GetCddPlateImportRuntimeStatusDep,
) -> CddPlateImportStatusResponse:
    result = await runtime_status_uc(
        GetCddPlateImportRuntimeStatusQuery(
            workspace_id=auth.workspace_id,
            workflow_id=workflow_id,
        ),
        auth=auth,
    )
    data = result_to_response(result)
    return CddPlateImportStatusResponse(
        import_id=data.import_id,
        status=data.status,
        total_count=data.total_count,
        plates_registered=data.plates_registered,
        plates_duplicate=data.plates_duplicate,
        plates_error=data.plates_error,
        wells_mapped=data.wells_mapped,
        wells_unresolved=data.wells_unresolved,
        current_offset=data.current_offset,
        pages_processed=data.pages_processed,
    )


@router.post("/{workflow_id}/cancel", status_code=204)
async def cancel_cdd_plate_import(
    auth: AuthDep,
    workflow_id: str,
    cancel_uc: CancelCddPlateImportDep,
) -> None:
    result = await cancel_uc(
        CancelCddPlateImportCommand(
            workspace_id=auth.workspace_id,
            workflow_id=workflow_id,
        ),
        auth=auth,
    )
    result_to_response(result)


@router.post("/{import_id}/force-fail", status_code=204)
async def force_fail_cdd_plate_import(
    auth: AuthDep,
    use_case: ForceFailCddPlateImportDep,
    import_id: str,
) -> None:
    from cellar.application.cdd_import.force_fail_cdd_plate_import import (
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
