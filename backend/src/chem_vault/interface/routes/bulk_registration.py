"""Bulk registration API routes.

Supports both async (Temporal, 202) and sync (fallback, 201) modes.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from chem_vault.application.chemical_registration.bulk_registration_service import (
    BulkRegistrationItem,
    BulkRegistrationItemResult,
    StartBulkRegistrationCommand,
)
from chem_vault.domain.chemical_registration.enums import BulkRegistrationFileFormat
from chem_vault.infrastructure.parsers.chemical_file_parser import get_parser
from chem_vault.interface.dependencies import AuthDep, BulkRegistrationServiceDep
from chem_vault.interface.error_handlers import result_to_response

router = APIRouter(prefix="/api/v1/bulk-registrations", tags=["bulk-registration"])


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class BulkRegistrationItemResponse(BaseModel):
    row_index: int
    success: bool
    is_new: bool = False
    molecule_id: uuid.UUID | None = None
    batch_id: uuid.UUID | None = None
    batch_number: str | None = None
    salt_matched: bool = False
    error: str | None = None

    @classmethod
    def from_item(cls, item: BulkRegistrationItemResult) -> BulkRegistrationItemResponse:
        return cls(
            row_index=item.row_index,
            success=item.success,
            is_new=item.is_new,
            molecule_id=item.molecule_id,
            batch_id=item.batch_id,
            batch_number=item.batch_number,
            salt_matched=item.salt_matched,
            error=item.error,
        )


class BulkRegistrationResponse(BaseModel):
    id: uuid.UUID
    status: str
    total_count: int
    registered_count: int
    duplicate_count: int
    error_count: int
    items: list[BulkRegistrationItemResponse]


class BulkRegistrationAcceptedResponse(BaseModel):
    workflow_id: str
    status: str = "processing"
    message: str = "File uploaded. Import running in background."


class BulkRegistrationStatusResponse(BaseModel):
    bulk_reg_id: str
    status: str
    total_count: int
    registered_count: int
    duplicate_count: int
    error_count: int
    disclosed_count: int = 0
    merge_candidate_count: int = 0
    conflict_count: int = 0
    merge_candidates: list[dict] = []
    chunks_processed: int
    chunks_total: int


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.post("")
async def start_bulk_registration(
    request: Request,
    auth: AuthDep,
    service: BulkRegistrationServiceDep,
    file: UploadFile = File(...),
    originating_org_id: uuid.UUID = Form(...),
    file_format: str = Form(...),
) -> JSONResponse:
    """Upload a file (SDF, CSV, XLSX) to register molecules in bulk.

    Returns 202 when Temporal is available (async), 201 otherwise (sync).
    """
    content = await file.read()
    if len(content) > 50 * 1024 * 1024:  # 50 MB
        raise HTTPException(status_code=413, detail="File too large (max 50 MB)")

    fmt = BulkRegistrationFileFormat(file_format)
    temporal_client = getattr(request.app.state, "temporal_client", None)

    # --- Async path (Temporal available) ---
    if temporal_client is not None:
        from chem_vault.infrastructure.temporal.activities.file_parsing import save_upload_to_storage
        from chem_vault.infrastructure.temporal.workflows.bulk_registration import (
            BulkRegistrationWorkflow,
            BulkRegistrationWorkflowInput,
        )

        storage_path = save_upload_to_storage(content, file.filename or "unknown")
        workflow_id = f"bulk-reg-{uuid.uuid4()}"

        await temporal_client.start_workflow(
            BulkRegistrationWorkflow.run,
            BulkRegistrationWorkflowInput(
                workspace_id=str(auth.workspace_id),
                originating_org_id=str(originating_org_id),
                submitted_by=str(auth.user_id),
                source_file=file.filename or "unknown",
                file_format=file_format,
                storage_path=storage_path,
                filename=file.filename or "unknown",
            ),
            id=workflow_id,
            task_queue="chem-vault-main",
        )

        body = BulkRegistrationAcceptedResponse(workflow_id=workflow_id)
        return JSONResponse(status_code=202, content=body.model_dump())

    # --- Sync fallback (no Temporal) ---
    parser = get_parser(fmt)
    parsed = parser.parse(content, file.filename or "unknown")

    items = [
        BulkRegistrationItem(
            row_index=p.row_index,
            name=p.name,
            smiles=p.smiles,
            molecule_type=p.molecule_type,
            external_ids=p.external_ids,
            error=p.error,
            amount_value=p.amount_value,
            amount_unit=p.amount_unit,
            salt_code=p.salt_code,
            salt_stoichiometry=p.salt_stoichiometry,
            purity=p.purity,
            batch_source=p.batch_source,
            appearance=p.appearance,
        )
        for p in parsed
    ]

    cmd = StartBulkRegistrationCommand(
        workspace_id=auth.workspace_id,
        source_file=file.filename or "unknown",
        file_format=file_format,
        items=items,
        submitted_by=auth.user_id,
        originating_org_id=originating_org_id,
    )

    result = await service(cmd, auth=auth)
    outcome = result_to_response(result)

    body = BulkRegistrationResponse(
        id=outcome.bulk_registration.id,
        status=outcome.bulk_registration.status.value,
        total_count=outcome.bulk_registration.total_count,
        registered_count=outcome.bulk_registration.registered_count,
        duplicate_count=outcome.bulk_registration.duplicate_count,
        error_count=outcome.bulk_registration.error_count,
        items=[BulkRegistrationItemResponse.from_item(i) for i in outcome.item_results],
    )
    return JSONResponse(status_code=201, content=body.model_dump(mode="json"))


@router.get("/{workflow_id}/status", response_model=BulkRegistrationStatusResponse)
async def get_bulk_registration_status(
    request: Request,
    auth: AuthDep,
    workflow_id: str,
) -> BulkRegistrationStatusResponse:
    """Poll progress of an async bulk registration workflow."""
    temporal_client = getattr(request.app.state, "temporal_client", None)
    if temporal_client is None:
        raise HTTPException(status_code=503, detail="Temporal is not available.")

    try:
        from chem_vault.infrastructure.temporal.workflows.bulk_registration import BulkRegistrationWorkflow

        handle = temporal_client.get_workflow_handle(workflow_id)
        progress = await handle.query(BulkRegistrationWorkflow.get_progress)
    except Exception as exc:
        raise HTTPException(status_code=404, detail=f"Workflow not found: {workflow_id}") from exc

    return BulkRegistrationStatusResponse(
        bulk_reg_id=progress.bulk_reg_id,
        status=progress.status,
        total_count=progress.total_count,
        registered_count=progress.registered_count,
        duplicate_count=progress.duplicate_count,
        error_count=progress.error_count,
        disclosed_count=progress.disclosed_count,
        merge_candidate_count=progress.merge_candidate_count,
        conflict_count=progress.conflict_count,
        merge_candidates=progress.merge_candidates,
        chunks_processed=progress.chunks_processed,
        chunks_total=progress.chunks_total,
    )
