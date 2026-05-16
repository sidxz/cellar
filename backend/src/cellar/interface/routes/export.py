"""Unified export endpoints (CSV / SDF / XLSX / PDF) — and the legacy
/molecules/export/sdf shim that now returns 410 Gone."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field

from cellar.application.export.cancel_export import CancelExportCommand
from cellar.application.export.get_export_status import GetExportStatusQuery
from cellar.application.export.list_exports import ListExportsQuery
from cellar.application.export.prepare_export_download import PrepareExportDownloadQuery
from cellar.application.export.start_export import StartExportCommand
from cellar.domain.export.enums import ExportFormat, ExportSource, ExportStatus
from cellar.interface.dependencies import AuthDep
from cellar.interface.dependencies._export import (
    CancelExportDep,
    GetExportStatusDep,
    ListExportsDep,
    PrepareExportDownloadDep,
    StartExportDep,
    StorageDep,
)
from cellar.interface.error_handlers import result_to_response

router = APIRouter(prefix="/api/v1/exports", tags=["export"])


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------


class StartExportBody(BaseModel):
    source: ExportSource = Field(default=ExportSource.SEARCH)
    format: ExportFormat
    filename_hint: str | None = None
    payload: dict[str, Any]


class StartExportResponse(BaseModel):
    job_id: uuid.UUID


class ExportStatusResponse(BaseModel):
    id: uuid.UUID
    status: ExportStatus
    format: ExportFormat
    row_count: int | None
    progress: float | None
    error_message: str | None
    download_url: str | None
    byte_size: int | None
    filename: str | None
    requested_at: datetime
    completed_at: datetime | None
    expires_at: datetime | None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("", response_model=StartExportResponse, status_code=202)
async def start_export(
    body: StartExportBody,
    auth: AuthDep,
    uc: StartExportDep,
) -> StartExportResponse:
    """Initiate an async export job. Returns a job_id for polling."""
    res = await uc(
        StartExportCommand(
            workspace_id=auth.workspace_id,
            requested_by=auth.user_id,
            source=body.source,
            format=body.format,
            payload=body.payload,
            filename_hint=body.filename_hint,
        ),
        auth=auth,
    )
    out = result_to_response(res)
    return StartExportResponse(job_id=out.job_id)


@router.get("", response_model=list[ExportStatusResponse])
async def list_exports(
    auth: AuthDep,
    uc: ListExportsDep,
    limit: int = Query(50, ge=1, le=200),
) -> list[ExportStatusResponse]:
    """List recent export jobs for the workspace, newest first."""
    res = await uc(
        ListExportsQuery(workspace_id=auth.workspace_id, limit=limit),
        auth=auth,
    )
    views = result_to_response(res)
    return [ExportStatusResponse(**v.__dict__) for v in views]


@router.get("/{job_id}", response_model=ExportStatusResponse)
async def get_export(
    job_id: uuid.UUID,
    auth: AuthDep,
    uc: GetExportStatusDep,
) -> ExportStatusResponse:
    """Poll the status of a single export job."""
    res = await uc(
        GetExportStatusQuery(workspace_id=auth.workspace_id, job_id=job_id),
        auth=auth,
    )
    view = result_to_response(res)
    return ExportStatusResponse(**view.__dict__)


@router.post("/{job_id}/cancel", status_code=204)
async def cancel_export(
    job_id: uuid.UUID,
    auth: AuthDep,
    uc: CancelExportDep,
) -> Response:
    """Request cancellation of an in-flight export job."""
    res = await uc(
        CancelExportCommand(workspace_id=auth.workspace_id, job_id=job_id),
        auth=auth,
    )
    result_to_response(res)
    return Response(status_code=204)


@router.get("/{job_id}/download")
async def download_export(
    job_id: uuid.UUID,
    auth: AuthDep,
    prepare_uc: PrepareExportDownloadDep,
    storage: StorageDep,
) -> Response:
    """Stream the completed export file. Returns 409 if not ready, 410 if expired."""
    res = await prepare_uc(
        PrepareExportDownloadQuery(workspace_id=auth.workspace_id, job_id=job_id),
        auth=auth,
    )
    info = result_to_response(res)
    data = await storage.download(info.file_key)
    return Response(
        content=data,
        media_type=info.content_type,
        headers={"Content-Disposition": f'attachment; filename="{info.filename}"'},
    )


# ---------------------------------------------------------------------------
# Legacy shim — kept for one release so existing FE callers get a clear error
# instead of a 404 / 405.
# ---------------------------------------------------------------------------

legacy_router = APIRouter(prefix="/api/v1/molecules/export", tags=["export-legacy"])


@legacy_router.post("/sdf", status_code=410)
async def legacy_sdf_export() -> Response:
    """Deprecated SDF export endpoint — use POST /api/v1/exports with format=sdf."""
    return Response(
        status_code=410,
        content=b'{"detail":"Use POST /api/v1/exports with format=sdf, source=search."}',
        media_type="application/json",
    )
