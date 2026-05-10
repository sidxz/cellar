"""Bulk registration API routes.

Supports both async (Temporal, 202) and sync (fallback, 201) modes — the
branching lives inside the ``StartBulkRegistration`` use case; this layer
just inspects the result mode to pick a response code.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, File, Form, Query, UploadFile, status
from pydantic import BaseModel
from returns.result import Failure

from chem_vault.application.chemical_registration.bulk_registration_service import (
    BulkRegistrationItemResult,
)
from chem_vault.application.chemical_registration.confirm_disclosure import (
    ConfirmDisclosureCommand,
)
from chem_vault.application.chemical_registration.get_bulk_registration_runtime_status import (
    GetBulkRegistrationRuntimeStatusQuery,
)
from chem_vault.application.chemical_registration.list_bulk_registration_items import (
    ListBulkRegistrationItemsQuery,
)
from chem_vault.application.chemical_registration.preview_bulk_registration_file import (
    PreviewBulkRegistrationFileQuery,
)
from chem_vault.application.chemical_registration.reject_disclosure import (
    RejectDisclosureCommand,
)
from chem_vault.application.chemical_registration.start_bulk_registration import (
    StartBulkRegistrationFromFileCommand,
)
from chem_vault.domain.chemical_registration.enums import BulkRegistrationFileFormat
from chem_vault.domain.shared.errors import NotFoundError, ValidationError
from chem_vault.interface.dependencies import (
    AuthDep,
    ConfirmDisclosureDep,
    GetBulkRegistrationRuntimeStatusDep,
    ListBulkRegistrationItemsDep,
    PreviewBulkRegistrationFileDep,
    RejectDisclosureDep,
    StartBulkRegistrationDep,
)
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


class MergeDecisionInput(BaseModel):
    disclosure_id: uuid.UUID
    action: str  # "confirm" | "reject"
    reason: str | None = None


class ConfirmMergesBody(BaseModel):
    decisions: list[MergeDecisionInput]


class MergeDecisionResult(BaseModel):
    disclosure_id: uuid.UUID
    action: str
    success: bool
    error: str | None = None
    merged_into_molecule_id: uuid.UUID | None = None


class ConfirmMergesResponse(BaseModel):
    results: list[MergeDecisionResult]
    confirmed_count: int
    rejected_count: int
    error_count: int


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.post(
    "",
    responses={
        202: {"model": BulkRegistrationAcceptedResponse},
        201: {"model": BulkRegistrationResponse},
    },
)
async def start_bulk_registration(
    auth: AuthDep,
    use_case: StartBulkRegistrationDep,
    file: UploadFile = File(...),
    originating_org_id: uuid.UUID = Form(...),
    file_format: str = Form(...),
    create_batch_on_duplicate: bool | None = Form(None),
):
    """Upload a file (SDF, CSV, XLSX) to register molecules in bulk.

    Returns 202 when Temporal is available (async), 201 otherwise (sync).
    The use case branches on orchestrator availability; this handler
    inspects the result's ``mode`` to pick the response shape.
    """
    content = await file.read()
    filename = file.filename or "unknown"

    cmd = StartBulkRegistrationFromFileCommand(
        workspace_id=auth.workspace_id,
        originating_org_id=originating_org_id,
        submitted_by=auth.user_id,
        filename=filename,
        file_format=file_format,
        content=content,
        create_batch_on_duplicate=create_batch_on_duplicate,
    )

    result = await use_case(cmd, auth=auth)
    outcome = result_to_response(result)

    if outcome.mode == "async":
        return _accepted_response(outcome.workflow_id or "")

    sync = outcome.sync_outcome
    assert sync is not None  # mode == "sync" guarantees this
    return BulkRegistrationResponse(
        id=sync.bulk_registration.id,
        status=sync.bulk_registration.status.value,
        total_count=sync.bulk_registration.total_count,
        registered_count=sync.bulk_registration.registered_count,
        duplicate_count=sync.bulk_registration.duplicate_count,
        error_count=sync.bulk_registration.error_count,
        items=[BulkRegistrationItemResponse.from_item(i) for i in sync.item_results],
    )


def _accepted_response(workflow_id: str):
    """Build a 202-Accepted JSON response for the async Temporal path."""
    from fastapi.responses import JSONResponse
    body = BulkRegistrationAcceptedResponse(workflow_id=workflow_id)
    return JSONResponse(status_code=status.HTTP_202_ACCEPTED, content=body.model_dump())


@router.get("/{workflow_id}/status", response_model=BulkRegistrationStatusResponse)
async def get_bulk_registration_status(
    auth: AuthDep,
    workflow_id: str,
    runtime_status_uc: GetBulkRegistrationRuntimeStatusDep,
) -> BulkRegistrationStatusResponse:
    """Poll progress of an async bulk registration workflow."""
    _verify_workspace_prefix(workflow_id, auth.workspace_id)

    result = await runtime_status_uc(
        GetBulkRegistrationRuntimeStatusQuery(
            workspace_id=auth.workspace_id,
            workflow_id=workflow_id,
        ),
        auth=auth,
    )
    data = result_to_response(result)

    return BulkRegistrationStatusResponse(
        bulk_reg_id=data.bulk_reg_id,
        status=data.status,
        total_count=data.total_count,
        registered_count=data.registered_count,
        duplicate_count=data.duplicate_count,
        error_count=data.error_count,
        disclosed_count=data.disclosed_count,
        merge_candidate_count=data.merge_candidate_count,
        conflict_count=data.conflict_count,
        merge_candidates=data.merge_candidates,
        chunks_processed=data.chunks_processed,
        chunks_total=data.chunks_total,
    )


@router.post("/{workflow_id}/confirm-merges", response_model=ConfirmMergesResponse)
async def confirm_merges(
    auth: AuthDep,
    workflow_id: str,
    body: ConfirmMergesBody,
    confirm_uc: ConfirmDisclosureDep,
    reject_uc: RejectDisclosureDep,
) -> ConfirmMergesResponse:
    """Batch confirm or reject merge candidates from a bulk registration workflow."""
    _verify_workspace_prefix(workflow_id, auth.workspace_id)

    results: list[MergeDecisionResult] = []
    confirmed_count = 0
    rejected_count = 0
    error_count = 0

    for decision in body.decisions:
        if decision.action == "confirm":
            result = await confirm_uc(
                ConfirmDisclosureCommand(
                    workspace_id=auth.workspace_id,
                    disclosure_id=decision.disclosure_id,
                    confirmed_by=auth.user_id,
                ),
                auth=auth,
            )
            if isinstance(result, Failure):
                error = result.failure()
                results.append(
                    MergeDecisionResult(
                        disclosure_id=decision.disclosure_id,
                        action=decision.action,
                        success=False,
                        error=getattr(error, "message", str(error)),
                    )
                )
                error_count += 1
            else:
                outcome = result.unwrap()
                results.append(
                    MergeDecisionResult(
                        disclosure_id=decision.disclosure_id,
                        action=decision.action,
                        success=True,
                        merged_into_molecule_id=outcome.merged_into_molecule_id,
                    )
                )
                confirmed_count += 1

        elif decision.action == "reject":
            result = await reject_uc(
                RejectDisclosureCommand(
                    workspace_id=auth.workspace_id,
                    disclosure_id=decision.disclosure_id,
                    reason=decision.reason,
                    rejected_by=auth.user_id,
                ),
                auth=auth,
            )
            if isinstance(result, Failure):
                error = result.failure()
                results.append(
                    MergeDecisionResult(
                        disclosure_id=decision.disclosure_id,
                        action=decision.action,
                        success=False,
                        error=getattr(error, "message", str(error)),
                    )
                )
                error_count += 1
            else:
                results.append(
                    MergeDecisionResult(
                        disclosure_id=decision.disclosure_id,
                        action=decision.action,
                        success=True,
                    )
                )
                rejected_count += 1

        else:
            results.append(
                MergeDecisionResult(
                    disclosure_id=decision.disclosure_id,
                    action=decision.action,
                    success=False,
                    error=f"Unknown action '{decision.action}'. Must be 'confirm' or 'reject'.",
                )
            )
            error_count += 1

    return ConfirmMergesResponse(
        results=results,
        confirmed_count=confirmed_count,
        rejected_count=rejected_count,
        error_count=error_count,
    )


# ---------------------------------------------------------------------------
# Preview endpoint — parse-only, no persistence
# ---------------------------------------------------------------------------


class PreviewItem(BaseModel):
    row_index: int
    name: str | None = None
    smiles: str | None = None
    molecule_type: str = "small_molecule"
    external_ids: list[dict[str, str]] = []
    amount_value: float | None = None
    amount_unit: str = "mg"
    salt_code: str | None = None
    salt_stoichiometry: int = 1
    purity: float | None = None
    batch_source: str = "synthesized"
    appearance: str | None = None
    error: str | None = None


class PreviewBulkRegistrationResponse(BaseModel):
    total_count: int
    error_count: int
    items: list[PreviewItem]


def _detect_file_format(filename: str) -> BulkRegistrationFileFormat:
    lower = filename.lower()
    if lower.endswith(".csv"):
        return BulkRegistrationFileFormat.CSV
    if lower.endswith((".xlsx", ".xls")):
        return BulkRegistrationFileFormat.XLSX
    if lower.endswith((".sdf", ".sd")):
        return BulkRegistrationFileFormat.SDF
    raise ValidationError(
        f"Unsupported file extension on {filename!r} — use .csv, .xlsx, .sdf or .sd"
    )


@router.post("/preview", response_model=PreviewBulkRegistrationResponse)
async def preview_bulk_registration(
    auth: AuthDep,
    preview_uc: PreviewBulkRegistrationFileDep,
    file: UploadFile = File(...),
) -> PreviewBulkRegistrationResponse:
    """Parse a bulk-registration file without persisting anything.

    The wizard's Preview step uses this to show users what was parsed before
    they kick off the durable Temporal workflow. The same file gets uploaded
    again to ``POST /api/v1/bulk-registrations`` on confirm — the preview
    endpoint stores nothing.
    """
    filename = file.filename or "upload"
    fmt = _detect_file_format(filename)
    content = await file.read()

    query = PreviewBulkRegistrationFileQuery(
        workspace_id=auth.workspace_id,
        filename=filename,
        content=content,
        file_format=fmt,
    )
    result = await preview_uc(query, auth=auth)
    outcome = result_to_response(result)

    return PreviewBulkRegistrationResponse(
        total_count=outcome.total_count,
        error_count=outcome.error_count,
        items=[
            PreviewItem(
                row_index=i.row_index,
                name=i.name,
                smiles=i.smiles,
                molecule_type=i.molecule_type,
                external_ids=i.external_ids,
                amount_value=i.amount_value,
                amount_unit=i.amount_unit,
                salt_code=i.salt_code,
                salt_stoichiometry=i.salt_stoichiometry,
                purity=i.purity,
                batch_source=i.batch_source,
                appearance=i.appearance,
                error=i.error,
            )
            for i in outcome.items
        ],
    )


# ---------------------------------------------------------------------------
# Per-row items endpoint — drives the Summary tab
# ---------------------------------------------------------------------------


class BulkRegItemRowResponse(BaseModel):
    row_index: int
    action: str
    success: bool
    molecule_id: uuid.UUID | None = None
    molecule_name: str | None = None
    registration_number: str | None = None
    batch_id: uuid.UUID | None = None
    batch_number: str | None = None
    error: str | None = None


class ListBulkRegItemsResponse(BaseModel):
    rows: list[BulkRegItemRowResponse]
    total: int
    limit: int
    offset: int


@router.get("/{workflow_id}/items", response_model=ListBulkRegItemsResponse)
async def list_bulk_registration_items(
    auth: AuthDep,
    list_uc: ListBulkRegistrationItemsDep,
    workflow_id: str,
    action: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> ListBulkRegItemsResponse:
    """Paged per-row outcomes for a bulk registration job.

    Filterable by action (registered / deduplicated / disclosed /
    merge_candidate / conflict / error) so the Summary tabs can drill into
    each bucket.
    """
    _verify_workspace_prefix(workflow_id, auth.workspace_id)

    query = ListBulkRegistrationItemsQuery(
        workspace_id=auth.workspace_id,
        workflow_id=workflow_id,
        action=action,
        limit=limit,
        offset=offset,
    )
    result = await list_uc(query, auth=auth)
    page = result_to_response(result)

    return ListBulkRegItemsResponse(
        rows=[
            BulkRegItemRowResponse(
                row_index=r.row_index,
                action=r.action,
                success=r.success,
                molecule_id=r.molecule_id,
                molecule_name=r.molecule_name,
                registration_number=r.registration_number,
                batch_id=r.batch_id,
                batch_number=r.batch_number,
                error=r.error,
            )
            for r in page.rows
        ],
        total=page.total,
        limit=limit,
        offset=offset,
    )


def _verify_workspace_prefix(workflow_id: str, workspace_id: uuid.UUID) -> None:
    """Verify the workflow belongs to the requesting workspace.

    Workflow IDs have the format: ``bulk-reg-{workspace_id}-{uuid}``.
    """
    prefix = "bulk-reg-"
    if not workflow_id.startswith(prefix):
        raise NotFoundError("Workflow", workflow_id)
    remainder = workflow_id[len(prefix) :]
    if len(remainder) < 37 or remainder[:36] != str(workspace_id):
        raise NotFoundError("Workflow", workflow_id)
