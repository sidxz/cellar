"""Plate data import endpoints + ImportTemplate CRUD."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, UploadFile
from lagom import Container
from pydantic import BaseModel

from chem_vault.application.inventory.import_plate_data import (
    ImportExecutionResult,
    ImportFileCache,
    ImportPlateDataService,
    ImportPreview,
    ValidationResult,
    auto_match_template,
    preview_import_file,
)
from chem_vault.application.inventory.import_templates import (
    CreateImportTemplate,
    CreateImportTemplateCommand,
    DeleteImportTemplate,
    DeleteImportTemplateCommand,
    ListImportTemplates,
    ListImportTemplatesQuery,
)
from chem_vault.domain.inventory.import_template import ImportTemplate
from chem_vault.interface.dependencies import AuthDep, get_container
from chem_vault.interface.error_handlers import result_to_response

router = APIRouter(prefix="/api/v1", tags=["plate-import"])


# ---------------------------------------------------------------------------
# Response / request models
# ---------------------------------------------------------------------------


class ImportPreviewResponse(BaseModel):
    file_id: str
    filename: str
    headers: list[str]
    preview_rows: list[list[str]]
    row_count: int
    suggested_template_id: str | None = None
    suggested_template_name: str | None = None


class ValidateImportBody(BaseModel):
    file_id: str
    column_mappings: dict[str, str]
    protocol_id: uuid.UUID | None = None
    run_id: uuid.UUID | None = None


class ValidationDetailResponse(BaseModel):
    row: int
    issue: str
    severity: str


class ValidationResultResponse(BaseModel):
    total_rows: int
    matched: int
    unresolved: int
    errors: int
    details: list[ValidationDetailResponse]


class ExecuteImportBody(BaseModel):
    file_id: str
    column_mappings: dict[str, str]
    protocol_id: uuid.UUID | None = None
    run_id: uuid.UUID | None = None


class ExecuteImportResponse(BaseModel):
    imported_count: int
    skipped_count: int
    readout_count: int = 0
    errors: list[str]


class ImportTemplateResponse(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    name: str
    description: str | None = None
    column_mappings: dict
    default_protocol_id: uuid.UUID | None = None
    created_by: uuid.UUID

    @classmethod
    def from_domain(cls, t: ImportTemplate) -> ImportTemplateResponse:
        return cls(
            id=t.id,
            workspace_id=t.workspace_id,
            name=t.name,
            description=t.description,
            column_mappings=t.column_mappings,
            default_protocol_id=t.default_protocol_id,
            created_by=t.created_by,
        )


class CreateImportTemplateBody(BaseModel):
    name: str
    column_mappings: dict
    description: str | None = None
    default_protocol_id: uuid.UUID | None = None


# ---------------------------------------------------------------------------
# Use-case / service dependencies
# ---------------------------------------------------------------------------


def _import_file_cache(
    c: Annotated[Container, Depends(get_container)],
) -> ImportFileCache:
    return c[ImportFileCache]


def _import_plate_data_service(
    c: Annotated[Container, Depends(get_container)],
) -> ImportPlateDataService:
    return c[ImportPlateDataService]


def _create_import_template(
    c: Annotated[Container, Depends(get_container)],
) -> CreateImportTemplate:
    return c[CreateImportTemplate]


def _list_import_templates(
    c: Annotated[Container, Depends(get_container)],
) -> ListImportTemplates:
    return c[ListImportTemplates]


def _delete_import_template(
    c: Annotated[Container, Depends(get_container)],
) -> DeleteImportTemplate:
    return c[DeleteImportTemplate]


# ---------------------------------------------------------------------------
# Import pipeline endpoints
# ---------------------------------------------------------------------------


@router.post("/plates/import/preview", response_model=ImportPreviewResponse)
async def preview_import(
    auth: AuthDep,
    file: UploadFile = File(...),
    list_uc: Annotated[ListImportTemplates, Depends(_list_import_templates)] = ...,
    cache: Annotated[ImportFileCache, Depends(_import_file_cache)] = ...,
) -> ImportPreviewResponse:
    content = await file.read()
    preview: ImportPreview = result_to_response(
        preview_import_file(file.filename or "upload.csv", content, cache, workspace_id=auth.workspace_id)
    )

    # Auto-match against saved templates using header similarity
    suggested_id: str | None = None
    suggested_name: str | None = None
    try:
        templates_result = await list_uc(
            ListImportTemplatesQuery(workspace_id=auth.workspace_id)
        )
        from returns.result import Success

        if isinstance(templates_result, Success):
            templates: list[ImportTemplate] = templates_result.unwrap()
            suggested_id, suggested_name = auto_match_template(preview.headers, templates)
    except Exception:
        # Auto-matching is best-effort; never fail the preview because of it
        pass

    return ImportPreviewResponse(
        file_id=preview.file_id,
        filename=preview.filename,
        headers=preview.headers,
        preview_rows=preview.preview_rows,
        row_count=preview.row_count,
        suggested_template_id=suggested_id,
        suggested_template_name=suggested_name,
    )


@router.post("/plates/import/validate", response_model=ValidationResultResponse)
async def validate_import(
    body: ValidateImportBody,
    auth: AuthDep,
    service: Annotated[ImportPlateDataService, Depends(_import_plate_data_service)],
) -> ValidationResultResponse:
    result: ValidationResult = result_to_response(
        await service.validate(
            file_id=body.file_id,
            column_mappings=body.column_mappings,
            workspace_id=auth.workspace_id,
        )
    )

    return ValidationResultResponse(
        total_rows=result.total_rows,
        matched=result.matched,
        unresolved=result.unresolved,
        errors=result.errors,
        details=[
            ValidationDetailResponse(row=d.row, issue=d.issue, severity=d.severity)
            for d in result.details
        ],
    )


@router.post("/plates/import/execute", response_model=ExecuteImportResponse)
async def execute_import_data(
    body: ExecuteImportBody,
    auth: AuthDep,
    service: Annotated[ImportPlateDataService, Depends(_import_plate_data_service)],
) -> ExecuteImportResponse:
    result: ImportExecutionResult = result_to_response(
        await service.execute(
            file_id=body.file_id,
            column_mappings=body.column_mappings,
            workspace_id=auth.workspace_id,
            protocol_id=body.protocol_id,
            run_id=body.run_id,
            auth=auth,
        )
    )
    return ExecuteImportResponse(
        imported_count=result.imported_count,
        skipped_count=result.skipped_count,
        readout_count=result.readout_count,
        errors=result.errors,
    )


# ---------------------------------------------------------------------------
# Import template CRUD endpoints
# ---------------------------------------------------------------------------


@router.get("/import-templates", response_model=list[ImportTemplateResponse])
async def list_import_templates(
    auth: AuthDep,
    uc: Annotated[ListImportTemplates, Depends(_list_import_templates)],
) -> list[ImportTemplateResponse]:
    templates = result_to_response(
        await uc(ListImportTemplatesQuery(workspace_id=auth.workspace_id))
    )
    return [ImportTemplateResponse.from_domain(t) for t in templates]


@router.post(
    "/import-templates", response_model=ImportTemplateResponse, status_code=201
)
async def create_import_template(
    body: CreateImportTemplateBody,
    auth: AuthDep,
    uc: Annotated[CreateImportTemplate, Depends(_create_import_template)],
) -> ImportTemplateResponse:
    template = result_to_response(
        await uc(
            CreateImportTemplateCommand(
                workspace_id=auth.workspace_id,
                name=body.name,
                column_mappings=body.column_mappings,
                description=body.description,
                default_protocol_id=body.default_protocol_id,
                created_by=auth.user_id,
            ),
            auth=auth,
        )
    )
    return ImportTemplateResponse.from_domain(template)


@router.delete("/import-templates/{template_id}", status_code=204)
async def delete_import_template(
    template_id: uuid.UUID,
    auth: AuthDep,
    uc: Annotated[DeleteImportTemplate, Depends(_delete_import_template)],
) -> None:
    result_to_response(
        await uc(
            DeleteImportTemplateCommand(
                workspace_id=auth.workspace_id,
                template_id=template_id,
            ),
            auth=auth,
        )
    )
