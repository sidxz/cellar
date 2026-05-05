"""Long-format run-file import routes + RunImportTemplate CRUD."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, File, Form, UploadFile
from pydantic import BaseModel, Field

from chem_vault.application.screening.import_run_file import (
    ImportRunFileCommand,
    ImportRunFileResult,
    PreviewRunFileQuery,
    PreviewRunFileResult,
)
from chem_vault.application.screening.long_format_normalizer import (
    ColumnMapping,
    ReadoutColumn,
)
from chem_vault.application.screening.run_import_templates import (
    CreateRunImportTemplateCommand,
    DeleteRunImportTemplateCommand,
    ListRunImportTemplatesQuery,
    UpdateRunImportTemplateCommand,
)
from chem_vault.interface.dependencies import (
    AuthDep,
    CreateRunImportTemplateDep,
    DeleteRunImportTemplateDep,
    ImportRunFileDep,
    ListRunImportTemplatesDep,
    PreviewRunFileDep,
    UpdateRunImportTemplateDep,
)
from chem_vault.interface.error_handlers import result_to_response

router = APIRouter(prefix="/api/v1", tags=["run-import"])


# ---------------------------------------------------------------------------
# Preview
# ---------------------------------------------------------------------------


class HeaderSuggestionModel(BaseModel):
    header: str
    role: str | None
    confidence: str
    reason: str = ""


class PlatePreviewModel(BaseModel):
    plate_name: str
    plate_format: str
    well_count: int
    sample_count: int
    blank_count: int


class PreviewRunFileResponse(BaseModel):
    preview_id: uuid.UUID
    headers: list[str]
    suggestions: list[HeaderSuggestionModel]
    sample_rows: list[dict[str, str]]
    plates: list[PlatePreviewModel]
    matched_batches: int
    unmatched_batches: list[str]
    total_rows: int
    expires_in_seconds: int


@router.post(
    "/runs/{run_id}/preview-file",
    response_model=PreviewRunFileResponse,
    status_code=200,
)
async def preview_run_file(
    run_id: uuid.UUID,
    auth: AuthDep,
    file: Annotated[UploadFile, File()],
    uc: PreviewRunFileDep,
    concentration_unit: Annotated[str, Form()] = "uM",
) -> PreviewRunFileResponse:
    """Parse a long-format run file and return a preview + ``preview_id``.

    Accepts ``.xlsx`` or ``.csv`` uploads. The returned ``preview_id`` is
    valid for ~60 seconds and must be passed to ``POST /import-file`` to
    actually persist the data.
    """
    content = await file.read()
    query = PreviewRunFileQuery(
        workspace_id=auth.workspace_id,
        run_id=run_id,
        file_content=content,
        filename=file.filename or "",
        concentration_unit=concentration_unit,
    )
    result = await uc(query, auth=auth)
    preview: PreviewRunFileResult = result_to_response(result)
    return PreviewRunFileResponse(
        preview_id=preview.preview_id,
        headers=list(preview.headers),
        suggestions=[
            HeaderSuggestionModel(
                header=s.header,
                role=s.role,
                confidence=s.confidence,
                reason=s.reason,
            )
            for s in preview.suggestions
        ],
        sample_rows=list(preview.sample_rows),
        plates=[
            PlatePreviewModel(
                plate_name=p.plate_name,
                plate_format=p.plate_format,
                well_count=p.well_count,
                sample_count=p.sample_count,
                blank_count=p.blank_count,
            )
            for p in preview.plates
        ],
        matched_batches=preview.matched_batches,
        unmatched_batches=list(preview.unmatched_batches),
        total_rows=preview.total_rows,
        expires_in_seconds=preview.expires_in_seconds,
    )


# ---------------------------------------------------------------------------
# Import
# ---------------------------------------------------------------------------


class ReadoutColumnRequest(BaseModel):
    header: str
    readout_definition_id: uuid.UUID


class ColumnMappingRequest(BaseModel):
    well: str
    plate_name: str | None = None
    concentration: str | None = None
    batch_ref: str | None = None
    scientist: str | None = None
    readout_columns: list[ReadoutColumnRequest] = Field(default_factory=list)


class ImportRunFileRequest(BaseModel):
    preview_id: uuid.UUID
    mapping: ColumnMappingRequest
    concentration_unit: str = "uM"
    replace_existing: bool = False


class ImportRunFileResponse(BaseModel):
    rows_total: int
    plates_created: int
    wells_created: int
    readouts_created: int
    unmatched_batches: list[str]
    controls_inferred: int
    skipped_rows: int


@router.post(
    "/runs/{run_id}/import-file",
    response_model=ImportRunFileResponse,
    status_code=201,
)
async def import_run_file(
    run_id: uuid.UUID,
    auth: AuthDep,
    body: ImportRunFileRequest,
    uc: ImportRunFileDep,
) -> ImportRunFileResponse:
    """Persist a previously-previewed long-format run file to the run."""
    mapping = ColumnMapping(
        well=body.mapping.well,
        plate_name=body.mapping.plate_name,
        concentration=body.mapping.concentration,
        batch_ref=body.mapping.batch_ref,
        scientist=body.mapping.scientist,
        readout_columns=tuple(
            ReadoutColumn(header=rc.header, readout_definition_id=rc.readout_definition_id)
            for rc in body.mapping.readout_columns
        ),
    )
    cmd = ImportRunFileCommand(
        workspace_id=auth.workspace_id,
        run_id=run_id,
        preview_id=body.preview_id,
        mapping=mapping,
        concentration_unit=body.concentration_unit,
        replace_existing=body.replace_existing,
    )
    result = await uc(cmd, auth=auth)
    out: ImportRunFileResult = result_to_response(result)
    return ImportRunFileResponse(
        rows_total=out.rows_total,
        plates_created=out.plates_created,
        wells_created=out.wells_created,
        readouts_created=out.readouts_created,
        unmatched_batches=out.unmatched_batches,
        controls_inferred=out.controls_inferred,
        skipped_rows=out.skipped_rows,
    )


# ---------------------------------------------------------------------------
# RunImportTemplate CRUD
# ---------------------------------------------------------------------------


class RunImportTemplateResponse(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    name: str
    description: str | None
    column_mapping: dict[str, Any]
    concentration_unit: str
    created_by: uuid.UUID
    created_at: datetime
    updated_at: datetime | None


class CreateRunImportTemplateRequest(BaseModel):
    name: str
    description: str | None = None
    column_mapping: dict[str, Any]
    concentration_unit: str = "uM"


class UpdateRunImportTemplateRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    column_mapping: dict[str, Any] | None = None
    concentration_unit: str | None = None


def _to_response(template) -> RunImportTemplateResponse:  # type: ignore[no-untyped-def]
    return RunImportTemplateResponse(
        id=template.id,
        workspace_id=template.workspace_id,
        name=template.name,
        description=template.description,
        column_mapping=template.column_mapping,
        concentration_unit=template.concentration_unit,
        created_by=template.created_by,
        created_at=template.created_at,
        updated_at=template.updated_at,
    )


@router.get("/run-import-templates", response_model=list[RunImportTemplateResponse])
async def list_run_import_templates(
    auth: AuthDep, uc: ListRunImportTemplatesDep
) -> list[RunImportTemplateResponse]:
    result = await uc(
        ListRunImportTemplatesQuery(workspace_id=auth.workspace_id),
        auth=auth,
    )
    templates = result_to_response(result)
    return [_to_response(t) for t in templates]


@router.post(
    "/run-import-templates",
    response_model=RunImportTemplateResponse,
    status_code=201,
)
async def create_run_import_template(
    auth: AuthDep,
    body: CreateRunImportTemplateRequest,
    uc: CreateRunImportTemplateDep,
) -> RunImportTemplateResponse:
    cmd = CreateRunImportTemplateCommand(
        workspace_id=auth.workspace_id,
        name=body.name,
        description=body.description,
        column_mapping=body.column_mapping,
        concentration_unit=body.concentration_unit,
        created_by=auth.user_id,
    )
    result = await uc(cmd, auth=auth)
    return _to_response(result_to_response(result))


@router.put("/run-import-templates/{template_id}", response_model=RunImportTemplateResponse)
async def update_run_import_template(
    template_id: uuid.UUID,
    auth: AuthDep,
    body: UpdateRunImportTemplateRequest,
    uc: UpdateRunImportTemplateDep,
) -> RunImportTemplateResponse:
    cmd = UpdateRunImportTemplateCommand(
        workspace_id=auth.workspace_id,
        template_id=template_id,
        name=body.name,
        description=body.description,
        column_mapping=body.column_mapping,
        concentration_unit=body.concentration_unit,
    )
    result = await uc(cmd, auth=auth)
    return _to_response(result_to_response(result))


@router.delete("/run-import-templates/{template_id}", status_code=204)
async def delete_run_import_template(
    template_id: uuid.UUID,
    auth: AuthDep,
    uc: DeleteRunImportTemplateDep,
) -> None:
    cmd = DeleteRunImportTemplateCommand(
        workspace_id=auth.workspace_id,
        template_id=template_id,
    )
    result = await uc(cmd, auth=auth)
    result_to_response(result)
