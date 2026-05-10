"""CDD molecule import API routes."""

from __future__ import annotations

import uuid

from fastapi import APIRouter
from pydantic import BaseModel

from chem_vault.application.cdd_import.cancel_cdd_molecule_import import (
    CancelCddMoleculeImportCommand,
)
from chem_vault.application.cdd_import.get_cdd_molecule_import_runtime_status import (
    GetCddMoleculeImportRuntimeStatusQuery,
)
from chem_vault.application.cdd_import.start_cdd_molecule_import import (
    StartCddMoleculeImportCommand,
)
from chem_vault.interface.dependencies import (
    AuthDep,
    CancelCddMoleculeImportDep,
    ForceFailCddMoleculeImportDep,
    GetCddMoleculeImportRuntimeStatusDep,
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
    auth: AuthDep,
    use_case: StartCddMoleculeImportDep,
    body: StartCddMoleculeImportBody,
) -> CddMoleculeImportAcceptedResponse:
    """Start a CDD vault molecule import. Returns 202 with workflow_id."""
    cmd = StartCddMoleculeImportCommand(
        workspace_id=auth.workspace_id,
        submitted_by=auth.user_id,
        originating_org_id=body.originating_org_id,
        import_mode=body.import_mode,
        filter_criteria=body.filter_criteria,
        max_molecules=body.max_molecules,
    )
    result = await use_case(cmd, auth=auth)
    outcome = result_to_response(result)
    return CddMoleculeImportAcceptedResponse(
        workflow_id=outcome.workflow_id,
        status="pending",
    )


@router.get("/{workflow_id}/status", response_model=CddMoleculeImportStatusResponse)
async def get_cdd_molecule_import_status(
    auth: AuthDep,
    workflow_id: str,
    runtime_status_uc: GetCddMoleculeImportRuntimeStatusDep,
) -> CddMoleculeImportStatusResponse:
    """Poll progress of a CDD molecule import workflow.

    Workspace ownership is enforced by the embedded ``workspace_id`` prefix
    in the workflow_id; the use case verifies the requesting workspace.
    """
    result = await runtime_status_uc(
        GetCddMoleculeImportRuntimeStatusQuery(
            workspace_id=auth.workspace_id,
            workflow_id=workflow_id,
        ),
        auth=auth,
    )
    data = result_to_response(result)
    return CddMoleculeImportStatusResponse(
        import_id=data.import_id,
        status=data.status,
        total_count=data.total_count,
        registered_count=data.registered_count,
        duplicate_count=data.duplicate_count,
        error_count=data.error_count,
        skipped_count=data.skipped_count,
        current_offset=data.current_offset,
        pages_processed=data.pages_processed,
    )


@router.post("/{workflow_id}/cancel", status_code=204)
async def cancel_cdd_molecule_import(
    auth: AuthDep,
    workflow_id: str,
    cancel_uc: CancelCddMoleculeImportDep,
) -> None:
    """Send a cancel signal to a running CDD molecule import workflow."""
    result = await cancel_uc(
        CancelCddMoleculeImportCommand(
            workspace_id=auth.workspace_id,
            workflow_id=workflow_id,
        ),
        auth=auth,
    )
    result_to_response(result)


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
