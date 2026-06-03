"""Long-format run-file import routes + RunImportTemplate CRUD."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, File, Form, UploadFile
from pydantic import BaseModel, Field
from pydantic import ValidationError as PydanticValidationError

from cellar.application.screening.import_run_file import (
    ImportRunFileCommand,
    ImportRunFileResult,
    PreviewRunFileQuery,
    PreviewRunFileResult,
    RepreviewRunFileQuery,
)
from cellar.application.screening.import_summary_file import ImportSummaryFileCommand
from cellar.application.screening.long_format_normalizer import (
    ColumnMapping,
    ReadoutColumn,
)
from cellar.application.screening.run_import_templates import (
    CreateRunImportTemplateCommand,
    DeleteRunImportTemplateCommand,
    ListRunImportTemplatesQuery,
    UpdateRunImportTemplateCommand,
)
from cellar.application.screening.summary_import_models import (
    SummaryColumnMapping,
    SummaryImportResult,
    SummaryPreviewResult,
)
from cellar.domain.shared.errors import ValidationError
from cellar.interface.dependencies import (
    AuthDep,
    CreateRunImportTemplateDep,
    DeleteRunImportTemplateDep,
    ImportRunFileDep,
    ImportSummaryFileDep,
    ListRunImportTemplatesDep,
    PreviewRunFileDep,
    PreviewSummaryFileDep,
    ReadoutCalculationEngineDep,
    RepreviewRunFileDep,
    UpdateRunImportTemplateDep,
)
from cellar.interface.error_handlers import result_to_response

router = APIRouter(prefix="/api/v1", tags=["run-import"])


# ---------------------------------------------------------------------------
# Preview
# ---------------------------------------------------------------------------


class HeaderSuggestionModel(BaseModel):
    header: str
    role: str | None
    confidence: str
    reason: str = ""
    # Set when the header's normalized name matches a protocol-defined
    # readout (numeric or text). The wizard pre-binds the readout-def
    # select from this id; no FE-side name matching needed.
    readout_definition_id: uuid.UUID | None = None


class PlatePreviewModel(BaseModel):
    plate_name: str
    plate_format: str
    well_count: int
    sample_count: int
    blank_count: int


class WellConflictModel(BaseModel):
    plate_name: str
    well_position: str
    reason: str


class ReadoutConflictModel(BaseModel):
    plate_name: str
    well_position: str
    readout_definition_id: uuid.UUID
    readout_name: str = ""


class BatchOptionModel(BaseModel):
    batch_id: uuid.UUID
    batch_number: str
    salt_form: str | None = None
    purity: float | None = None
    created_at: datetime


class AmbiguousCompoundModel(BaseModel):
    compound_ref: str
    molecule_id: uuid.UUID
    molecule_name: str
    batch_options: list[BatchOptionModel] = Field(default_factory=list)
    affected_row_count: int


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
    validation_errors: list[str] = Field(default_factory=list)
    will_create_plates: int = 0
    will_create_wells: int = 0
    will_create_readouts: int = 0
    will_skip_wells: list[WellConflictModel] = Field(default_factory=list)
    will_skip_readouts: list[ReadoutConflictModel] = Field(default_factory=list)
    matched_compounds: int = 0
    unmatched_compound_refs: list[str] = Field(default_factory=list)
    ambiguous_compounds: list[AmbiguousCompoundModel] = Field(default_factory=list)
    row_conflicts: list[str] = Field(default_factory=list)
    # Number of placeholder batches that would be auto-created if
    # auto_create_unmatched_batches=True is passed to the import step.
    # Always 0 when the preview query doesn't set that flag.
    auto_created_batches: int = 0


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
) -> PreviewRunFileResponse:
    """Parse a long-format run file and return a preview + ``preview_id``.

    Accepts ``.xlsx`` or ``.csv`` uploads. The returned ``preview_id`` is
    valid for ~60 seconds and must be passed to ``POST /import-file`` to
    actually persist the data.

    The dose unit is sourced from the run's protocol (``protocol.dose_unit``)
    — the wizard does not need to ask. Wells in the file are interpreted in
    that unit.
    """
    content = await file.read()
    query = PreviewRunFileQuery(
        workspace_id=auth.workspace_id,
        run_id=run_id,
        file_content=content,
        filename=file.filename or "",
        content_type=file.content_type or "",
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
                readout_definition_id=s.readout_definition_id,
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
        validation_errors=list(preview.validation_errors),
        will_create_plates=preview.will_create_plates,
        will_create_wells=preview.will_create_wells,
        will_create_readouts=preview.will_create_readouts,
        will_skip_wells=[
            WellConflictModel(
                plate_name=c.plate_name,
                well_position=c.well_position,
                reason=c.reason,
            )
            for c in preview.will_skip_wells
        ],
        will_skip_readouts=[
            ReadoutConflictModel(
                plate_name=c.plate_name,
                well_position=c.well_position,
                readout_definition_id=c.readout_definition_id,
                readout_name=c.readout_name,
            )
            for c in preview.will_skip_readouts
        ],
        matched_compounds=preview.matched_compounds,
        unmatched_compound_refs=list(preview.unmatched_compound_refs),
        ambiguous_compounds=[
            AmbiguousCompoundModel(
                compound_ref=a.compound_ref,
                molecule_id=a.molecule_id,
                molecule_name=a.molecule_name,
                batch_options=[
                    BatchOptionModel(
                        batch_id=b.batch_id,
                        batch_number=b.batch_number,
                        salt_form=b.salt_form,
                        purity=b.purity,
                        created_at=b.created_at,
                    )
                    for b in a.batch_options
                ],
                affected_row_count=a.affected_row_count,
            )
            for a in preview.ambiguous_compounds
        ],
        row_conflicts=list(preview.row_conflicts),
        auto_created_batches=preview.auto_created_batches,
    )


# ---------------------------------------------------------------------------
# Re-preview (after the chemist refines the column mapping)
# ---------------------------------------------------------------------------


class ReadoutColumnRequest(BaseModel):
    header: str
    readout_definition_id: uuid.UUID


class ColumnMappingRequest(BaseModel):
    well: str
    plate_name: str | None = None
    concentration: str | None = None
    batch_ref: str | None = None
    compound_ref: str | None = None
    readout_columns: list[ReadoutColumnRequest] = Field(default_factory=list)


class RepreviewRunFileRequest(BaseModel):
    preview_id: uuid.UUID
    mapping: ColumnMappingRequest


def _to_preview_response(preview: PreviewRunFileResult) -> PreviewRunFileResponse:
    return PreviewRunFileResponse(
        preview_id=preview.preview_id,
        headers=list(preview.headers),
        suggestions=[
            HeaderSuggestionModel(
                header=s.header,
                role=s.role,
                confidence=s.confidence,
                reason=s.reason,
                readout_definition_id=s.readout_definition_id,
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
        validation_errors=list(preview.validation_errors),
        will_create_plates=preview.will_create_plates,
        will_create_wells=preview.will_create_wells,
        will_create_readouts=preview.will_create_readouts,
        will_skip_wells=[
            WellConflictModel(
                plate_name=c.plate_name,
                well_position=c.well_position,
                reason=c.reason,
            )
            for c in preview.will_skip_wells
        ],
        will_skip_readouts=[
            ReadoutConflictModel(
                plate_name=c.plate_name,
                well_position=c.well_position,
                readout_definition_id=c.readout_definition_id,
                readout_name=c.readout_name,
            )
            for c in preview.will_skip_readouts
        ],
        matched_compounds=preview.matched_compounds,
        unmatched_compound_refs=list(preview.unmatched_compound_refs),
        ambiguous_compounds=[
            AmbiguousCompoundModel(
                compound_ref=a.compound_ref,
                molecule_id=a.molecule_id,
                molecule_name=a.molecule_name,
                batch_options=[
                    BatchOptionModel(
                        batch_id=b.batch_id,
                        batch_number=b.batch_number,
                        salt_form=b.salt_form,
                        purity=b.purity,
                        created_at=b.created_at,
                    )
                    for b in a.batch_options
                ],
                affected_row_count=a.affected_row_count,
            )
            for a in preview.ambiguous_compounds
        ],
        row_conflicts=list(preview.row_conflicts),
        auto_created_batches=preview.auto_created_batches,
    )


@router.post(
    "/runs/{run_id}/repreview-file",
    response_model=PreviewRunFileResponse,
    status_code=200,
)
async def repreview_run_file(
    run_id: uuid.UUID,
    auth: AuthDep,
    body: RepreviewRunFileRequest,
    uc: RepreviewRunFileDep,
) -> PreviewRunFileResponse:
    """Re-resolve a cached preview using the chemist's refined mapping.

    Called by the wizard when the chemist changes a column role in the
    mapping step (e.g. Batch Ref → Compound Ref). The original preview
    is reused without re-uploading the file; the response shape mirrors
    ``preview_run_file`` so the wizard can swap state in place.
    """
    mapping = ColumnMapping(
        well=body.mapping.well,
        plate_name=body.mapping.plate_name,
        concentration=body.mapping.concentration,
        batch_ref=body.mapping.batch_ref,
        compound_ref=body.mapping.compound_ref,
        readout_columns=tuple(
            ReadoutColumn(header=rc.header, readout_definition_id=rc.readout_definition_id)
            for rc in body.mapping.readout_columns
        ),
    )
    query = RepreviewRunFileQuery(
        workspace_id=auth.workspace_id,
        run_id=run_id,
        preview_id=body.preview_id,
        mapping=mapping,
    )
    result = await uc(query, auth=auth)
    preview: PreviewRunFileResult = result_to_response(result)
    return _to_preview_response(preview)


# ---------------------------------------------------------------------------
# Import
# ---------------------------------------------------------------------------


class CompoundBatchOverrideRequest(BaseModel):
    """One disambiguation pick. ``molecule_id`` -> ``batch_id``."""

    molecule_id: uuid.UUID
    batch_id: uuid.UUID


class ImportRunFileRequest(BaseModel):
    preview_id: uuid.UUID
    mapping: ColumnMappingRequest
    compound_batch_overrides: list[CompoundBatchOverrideRequest] = Field(default_factory=list)
    # When True, auto-create placeholder batches for unmatched batch refs
    # whose compound resolves to a known molecule. Defaults to False so the
    # chemist must explicitly opt in.
    auto_create_unmatched_batches: bool = False


class ImportRunFileResponse(BaseModel):
    rows_total: int
    plates_created: int
    wells_created: int
    readouts_created: int
    unmatched_batches: list[str]
    unmatched_compound_refs: list[str] = Field(default_factory=list)
    controls_from_template: int
    controls_unclassified: int
    skipped_rows: int
    conflicts_well_metadata: list[WellConflictModel] = Field(default_factory=list)
    conflicts_readout: list[ReadoutConflictModel] = Field(default_factory=list)
    attachment_id: uuid.UUID | None = None
    compute_warning: str | None = None
    attachment_warning: str | None = None
    fit_warnings: list[str] = Field(default_factory=list)
    # Number of placeholder batches auto-created during this import.
    # Always 0 when auto_create_unmatched_batches=False on the request.
    auto_created_batches: int = 0


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
        compound_ref=body.mapping.compound_ref,
        readout_columns=tuple(
            ReadoutColumn(header=rc.header, readout_definition_id=rc.readout_definition_id)
            for rc in body.mapping.readout_columns
        ),
    )
    overrides = {o.molecule_id: o.batch_id for o in body.compound_batch_overrides}
    cmd = ImportRunFileCommand(
        workspace_id=auth.workspace_id,
        run_id=run_id,
        preview_id=body.preview_id,
        mapping=mapping,
        compound_batch_overrides=overrides,
        auto_create_unmatched_batches=body.auto_create_unmatched_batches,
    )
    result = await uc(cmd, auth=auth)
    out: ImportRunFileResult = result_to_response(result)
    return ImportRunFileResponse(
        rows_total=out.rows_total,
        plates_created=out.plates_created,
        wells_created=out.wells_created,
        readouts_created=out.readouts_created,
        unmatched_batches=out.unmatched_batches,
        unmatched_compound_refs=out.unmatched_compound_refs,
        controls_from_template=out.controls_from_template,
        controls_unclassified=out.controls_unclassified,
        skipped_rows=out.skipped_rows,
        conflicts_well_metadata=[
            WellConflictModel(
                plate_name=c.plate_name,
                well_position=c.well_position,
                reason=c.reason,
            )
            for c in out.conflicts_well_metadata
        ],
        conflicts_readout=[
            ReadoutConflictModel(
                plate_name=c.plate_name,
                well_position=c.well_position,
                readout_definition_id=c.readout_definition_id,
                readout_name=c.readout_name,
            )
            for c in out.conflicts_readout
        ],
        attachment_id=out.attachment_id,
        compute_warning=out.compute_warning,
        attachment_warning=out.attachment_warning,
        fit_warnings=out.fit_warnings,
        auto_created_batches=out.auto_created_batches,
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
    created_by: uuid.UUID
    created_at: datetime
    updated_at: datetime | None


class CreateRunImportTemplateRequest(BaseModel):
    name: str
    description: str | None = None
    column_mapping: dict[str, Any]


class UpdateRunImportTemplateRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    column_mapping: dict[str, Any] | None = None


def _to_response(template) -> RunImportTemplateResponse:  # type: ignore[no-untyped-def]
    return RunImportTemplateResponse(
        id=template.id,
        workspace_id=template.workspace_id,
        name=template.name,
        description=template.description,
        column_mapping=template.column_mapping,
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


# ---------------------------------------------------------------------------
# Summary-results import (wide format: one value per compound x readout)
# ---------------------------------------------------------------------------


class SummaryHeaderSuggestionModel(BaseModel):
    header: str
    role: str
    confidence: str
    # Set when role == "readout" and the header's name matched a protocol
    # readout definition; the wizard pre-binds the select from this id.
    readout_definition_id: uuid.UUID | None = None
    note: str = ""


class SummaryPreviewResponse(BaseModel):
    headers: list[str]
    suggestions: list[SummaryHeaderSuggestionModel]
    sample_rows: list[dict[str, str]]
    total_rows: int
    matched_refs: int = 0
    unmatched_refs: list[str] = Field(default_factory=list)
    validation_errors: list[str] = Field(default_factory=list)

    @classmethod
    def from_result(cls, preview: SummaryPreviewResult) -> SummaryPreviewResponse:
        return cls(
            headers=list(preview.headers),
            suggestions=[
                SummaryHeaderSuggestionModel(
                    header=s.header,
                    role=s.role.value,
                    confidence=s.confidence,
                    readout_definition_id=s.readout_definition_id,
                    note=s.note,
                )
                for s in preview.suggestions
            ],
            sample_rows=list(preview.sample_rows),
            total_rows=preview.total_rows,
            matched_refs=preview.matched_refs,
            unmatched_refs=list(preview.unmatched_refs),
            validation_errors=list(preview.validation_errors),
        )


class SummaryImportErrorModel(BaseModel):
    row: str
    error: str


class SummaryImportResponse(BaseModel):
    rows_processed: int
    values_inserted: int
    values_updated: int
    rows_skipped: int
    errors: list[SummaryImportErrorModel] = Field(default_factory=list)

    @classmethod
    def from_result(cls, out: SummaryImportResult) -> SummaryImportResponse:
        return cls(
            rows_processed=out.rows_processed,
            values_inserted=out.values_inserted,
            values_updated=out.values_updated,
            rows_skipped=out.rows_skipped,
            errors=[
                SummaryImportErrorModel(row=e.get("row", ""), error=e.get("error", ""))
                for e in out.errors
            ],
        )


class SummaryColumnMappingRequest(BaseModel):
    """Confirmed column mapping the chemist sends back on import.

    ``readout_columns`` maps a file header to the readout-definition UUID the
    FE already holds (we never ask the user to type a UUID; the wizard picks a
    readout def by name and sends its id). Pydantic coerces the values to UUID.
    """

    compound_ref: str | None = None
    batch_ref: str | None = None
    readout_columns: dict[str, uuid.UUID] = Field(default_factory=dict)

    def to_domain(self) -> SummaryColumnMapping:
        return SummaryColumnMapping(
            compound_ref=self.compound_ref,
            batch_ref=self.batch_ref,
            readout_columns=dict(self.readout_columns),
        )


@router.post(
    "/runs/{run_id}/preview-summary-file",
    response_model=SummaryPreviewResponse,
    status_code=200,
)
async def preview_summary_file(
    run_id: uuid.UUID,
    auth: AuthDep,
    uc: PreviewSummaryFileDep,
    file: Annotated[UploadFile, File()],
) -> SummaryPreviewResponse:
    """Parse a wide-format summary file and suggest a per-column role mapping.

    Accepts ``.xlsx`` or ``.csv`` uploads. Returns the headers, a suggested
    role per column (compound_ref / batch_ref / readout / ignore, with the
    matched ``readout_definition_id`` when a header name lines up with a
    protocol readout), and a few sample rows. No writes — the chemist confirms
    the mapping and POSTs ``import-summary-file`` to commit.
    """
    content = await file.read()
    result = await uc(
        workspace_id=auth.workspace_id,
        run_id=run_id,
        filename=file.filename or "upload",
        content=content,
        auth=auth,
    )
    preview: SummaryPreviewResult = result_to_response(result)
    return SummaryPreviewResponse.from_result(preview)


@router.post(
    "/runs/{run_id}/import-summary-file",
    response_model=SummaryImportResponse,
    status_code=201,
)
async def import_summary_file(
    run_id: uuid.UUID,
    auth: AuthDep,
    uc: ImportSummaryFileDep,
    engine: ReadoutCalculationEngineDep,
    file: Annotated[UploadFile, File()],
    mapping: Annotated[str, Form()],
) -> SummaryImportResponse:
    """Commit wide-format summary endpoint values for a run (upsert, well-less).

    The ``mapping`` form field is the confirmed
    ``SummaryColumnMappingRequest`` JSON. After a successful import we trigger
    the readout calculation engine for the run so calculated readouts and
    dose-response artifacts refresh (mirrors ``/readout-data/bulk``).
    """
    content = await file.read()
    # Parse the mapping form field here so malformed JSON / non-UUID readout ids
    # surface as a domain ValidationError (HTTP 422) instead of a raw pydantic
    # ValidationError bubbling out as a 500.
    try:
        parsed_map = SummaryColumnMappingRequest.model_validate_json(mapping)
    except PydanticValidationError as exc:
        raise ValidationError(f"Invalid mapping: {exc}") from exc
    # NOTE: the use case's inserted/updated accounting compares a well-less-key
    # snapshot taken before/after the bulk upsert; this relies on READ COMMITTED
    # isolation (the default). A stricter isolation level would break the diff.
    cmd = ImportSummaryFileCommand(
        workspace_id=auth.workspace_id,
        run_id=run_id,
        filename=file.filename or "upload",
        content=content,
        mapping=parsed_map.to_domain(),
    )
    result = await uc(cmd, auth=auth)
    out: SummaryImportResult = result_to_response(result)

    # Refresh calculated readouts / DR artifacts for the affected run.
    await engine.compute_for_run(run_id, workspace_id=auth.workspace_id)

    return SummaryImportResponse.from_result(out)
