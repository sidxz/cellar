"""ImportRunFile — long-format run file import with preview/import gate.

Two flows:

- **Preview / repreview** (read-only): ``PreviewRunFile`` parses the
  upload, auto-guesses a column mapping, dry-resolves batch + compound
  references, summarizes plates and controls, and scans for conflicts
  against existing run state. The parsed table + raw bytes are stashed
  in a short-lived in-memory store keyed by ``preview_id``. The wizard
  surfaces the result for user confirmation. ``RepreviewRunFile`` re-runs
  the same resolution against the cached preview using a chemist-refined
  column mapping — no re-upload required.

- **Import** (write): ``ImportRunFile`` consumes a ``preview_id`` plus the
  user-confirmed ``ColumnMapping``. Re-runs the conflict scan as the
  source of truth, then writes only the non-conflicting plates, wells,
  and readouts. Conflicts are returned for reporting; nothing existing
  is overwritten. The raw uploaded bytes are persisted as a Run
  attachment on success so the file is part of the audit trail.

The preview store is in-memory only — preview payloads expire after 60s
and are deleted on first consume (idempotency on the import side).

Helpers live in sibling modules to keep this file focused on the import
orchestration:

- ``preview_run_file`` — ``PreviewRunFile`` + ``RepreviewRunFile`` use cases.
- ``import_run_file_preview_store`` — ``_StoredPreview``, ``PreviewStore``,
  ``InMemoryPreviewStore``, ``_guess_content_type``.
- ``import_run_file_dtos`` — Command / query / result dataclasses.
- ``import_run_file_mapper`` — row → resolver-index helpers.
- ``import_run_file_validator`` — control-layout validation rules.
- ``import_plan`` — conflict-scan dataclasses + the scan function itself.

All public names — both use cases, both DTO groups, the store, and the
import-plan conflict types — are re-exported from this module so the
original import path (``cellar.application.screening.import_run_file``)
remains the single canonical entry point for callers.
"""

from __future__ import annotations

import uuid

import structlog
from returns.result import Failure, Result, Success

from cellar.application.attachment.upload_attachment import (
    UploadAttachment,
    UploadAttachmentCommand,
)
from cellar.application.auth import AuthContext, require_editor
from cellar.application.screening.compound_ref_resolver import resolve_rows

# Re-exported here so existing callers `from import_run_file import WellConflict`
# keep working; the underscore-prefixed names are also re-imported for any
# tests/utilities that historically reached through this module.
from cellar.application.screening.import_plan import (  # noqa: F401
    ReadoutConflict,
    WellConflict,
    _ImportPlan,
    _ReadoutWrite,
    _scan_conflicts,
    _well_key,
    _well_metadata_mismatch,
)
from cellar.application.screening.import_run_file_dtos import (
    AmbiguousCompoundDTO,
    BatchOption,
    ImportRunFileCommand,
    ImportRunFileResult,
    PlatePreview,
    PreviewRunFileQuery,
    PreviewRunFileResult,
    RepreviewRunFileQuery,
)
from cellar.application.screening.import_run_file_mapper import (
    _auto_create_missing_batches,
    _build_batch_lookup,
    _build_compound_index,
)
from cellar.application.screening.import_run_file_preview_store import (
    InMemoryPreviewStore,
    PreviewStore,
    _guess_content_type,
    _StoredPreview,
)
from cellar.application.screening.import_run_file_validator import (
    _load_templates_by_format,
    _validate_controls_required,
)
from cellar.application.screening.long_format_normalizer import (
    ColumnMapping,
    NormalizedTable,
    ReadoutColumn,
    normalize,
)
from cellar.application.screening.preview_run_file import PreviewRunFile, RepreviewRunFile
from cellar.application.screening.readout_calculation_engine import (
    ReadoutCalculationEngine,
)
from cellar.application.shared.event_dispatcher import EventDispatcherProtocol
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.attachment.enums import AttachableType
from cellar.domain.chemical_registration.repository import MoleculeRepository
from cellar.domain.inventory.repository import BatchRepository
from cellar.domain.screening_assay.enums import ReadoutDataType
from cellar.domain.screening_assay.readout_data import ReadoutData
from cellar.domain.screening_assay.repository import (
    PlateTemplateRepository,
    ProtocolRepository,
    ReadoutDataRepository,
    RunRepository,
)
from cellar.domain.shared.errors import (
    ConflictError,
    DomainError,
    NotFoundError,
    ValidationError,
)

# Public surface. Re-exported so callers using the original
# `cellar.application.screening.import_run_file` import path keep
# working unchanged after the structural refactor.
__all__ = [
    "AmbiguousCompoundDTO",
    "BatchOption",
    "ImportRunFile",
    "ImportRunFileCommand",
    "ImportRunFileResult",
    "InMemoryPreviewStore",
    "PlatePreview",
    "PreviewRunFile",
    "PreviewRunFileQuery",
    "PreviewRunFileResult",
    "PreviewStore",
    "ReadoutConflict",
    "RepreviewRunFile",
    "RepreviewRunFileQuery",
    "WellConflict",
]

_log = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# ImportRunFile use case
# ---------------------------------------------------------------------------


class ImportRunFile:
    """Persist a previously-previewed long-format file to the run.

    Re-imports are non-destructive: existing plates are reused by name,
    existing wells are reused by `(plate, row, column)` if their metadata
    matches the file, and existing `(well, readout_def)` cells are never
    overwritten. Conflicts at any layer are skipped and reported.
    """

    def __init__(
        self,
        uow: UnitOfWork,
        run_repo: RunRepository,
        protocol_repo: ProtocolRepository,
        readout_data_repo: ReadoutDataRepository,
        batch_repo: BatchRepository,
        molecule_repo: MoleculeRepository,
        preview_store: PreviewStore,
        plate_template_repo: PlateTemplateRepository,
        upload_attachment: UploadAttachment,
        dispatcher: EventDispatcherProtocol | None = None,
        calculation_engine: ReadoutCalculationEngine | None = None,
        ensure_batch_exists=None,  # EnsureBatchExists | None; optional for back-compat
    ) -> None:
        self._uow = uow
        self._run_repo = run_repo
        self._protocol_repo = protocol_repo
        self._readout_data_repo = readout_data_repo
        self._batch_repo = batch_repo
        self._molecule_repo = molecule_repo
        self._store = preview_store
        self._plate_template_repo = plate_template_repo
        self._upload_attachment = upload_attachment
        self._dispatcher = dispatcher
        self._calc_engine = calculation_engine
        self._ensure_batch_exists = ensure_batch_exists

    async def __call__(
        self,
        input: ImportRunFileCommand,
        auth: AuthContext | None = None,
    ) -> Result[ImportRunFileResult, DomainError]:
        require_editor(auth)

        # Pull the preview here; the rest happens inside the UoW.
        preview = self._store.consume(input.preview_id)
        if preview is None:
            return Failure(NotFoundError("Preview", str(input.preview_id)))
        if preview.workspace_id != input.workspace_id or preview.run_id != input.run_id:
            return Failure(ValidationError("preview_id does not match this workspace + run"))

        async with self._uow:
            result = await self._execute(input, preview, auth)

        # Attachment + calc engine run in their own UoWs after the import
        # transaction commits. Both are best-effort — the import itself
        # has already succeeded if we got here.
        if isinstance(result, Success):
            unwrapped = result.unwrap()
            if unwrapped.readouts_created > 0 or unwrapped.wells_created > 0:
                await self._maybe_run_calc_engine(input, unwrapped)
            await self._maybe_attach_raw_file(input, preview, unwrapped, auth)
        return result

    async def _execute(
        self,
        cmd: ImportRunFileCommand,
        preview: _StoredPreview,
        auth: AuthContext | None,
    ) -> Result[ImportRunFileResult, DomainError]:
        # 1. Load the run with existing plates + wells.
        run = await self._run_repo.find_by_id_in_workspace(cmd.workspace_id, cmd.run_id)
        if run is None:
            return Failure(NotFoundError("Run", str(cmd.run_id)))
        if run.is_locked:
            return Failure(ConflictError("Cannot import into a locked run"))

        # 2. Load protocol — its dose_unit is the canonical unit.
        protocol = await self._protocol_repo.find_by_id_in_workspace(
            cmd.workspace_id, run.protocol_id
        )
        if protocol is None:
            return Failure(NotFoundError("Protocol", str(run.protocol_id)))

        # 3. Validate readout-def ids belong to this protocol; rebuild
        # readout columns with data_type so the normalizer parses each
        # column with the right value kind.
        rd_by_id = {rd.id: rd for rd in protocol.readout_definitions}
        typed_readouts: list[ReadoutColumn] = []
        for rc in cmd.mapping.readout_columns:
            rd = rd_by_id.get(rc.readout_definition_id)
            if rd is None:
                return Failure(
                    ValidationError(
                        f"readout_definition_id {rc.readout_definition_id} "
                        "does not belong to this run's protocol"
                    )
                )
            kind = "text" if rd.data_type == ReadoutDataType.TEXT else "numeric"
            typed_readouts.append(
                ReadoutColumn(
                    header=rc.header,
                    readout_definition_id=rc.readout_definition_id,
                    data_type=kind,
                )
            )
        typed_mapping = ColumnMapping(
            well=cmd.mapping.well,
            plate_name=cmd.mapping.plate_name,
            concentration=cmd.mapping.concentration,
            batch_ref=cmd.mapping.batch_ref,
            compound_ref=cmd.mapping.compound_ref,
            readout_columns=tuple(typed_readouts),
        )

        # 4. Normalize.
        normalized_result = normalize(preview.table, typed_mapping)
        if isinstance(normalized_result, Failure):
            return normalized_result
        normalized: NormalizedTable = normalized_result.unwrap()

        # 5. Pre-flight: control-layout coverage.
        templates_by_format = await _load_templates_by_format(
            protocol,
            normalized.plate_formats,
            cmd.workspace_id,
            self._plate_template_repo,
        )
        control_errors = _validate_controls_required(
            protocol, normalized.plate_formats, templates_by_format
        )
        if control_errors:
            return Failure(ValidationError("; ".join(control_errors)))

        # 6. Resolve batch + compound references with the chemist's
        # disambiguation overrides applied.
        batch_index = await _build_batch_lookup(
            normalized.rows,
            cmd.workspace_id,
            self._batch_repo,
        )
        compound_index = await _build_compound_index(
            normalized.rows,
            cmd.workspace_id,
            self._molecule_repo,
            self._batch_repo,
        )
        resolutions = resolve_rows(
            normalized.rows,
            batch_index=batch_index,
            compound_index=compound_index,
            overrides=cmd.compound_batch_overrides,
        )

        # 6b. Opt-in: auto-create placeholder batches for unmatched refs
        # whose compound is known, then re-resolve so the import picks up
        # the newly-created batches.
        auto_created_batches = 0
        if (
            cmd.auto_create_unmatched_batches
            and self._ensure_batch_exists is not None
            and resolutions.unmatched_batch_refs
            and auth is not None
        ):
            auto_created_batches = await _auto_create_missing_batches(
                normalized.rows,
                resolutions.unmatched_batch_refs,
                batch_index,
                compound_index,
                self._ensure_batch_exists,
                workspace_id=cmd.workspace_id,
                importing_user_id=auth.user_id,
                source_label=f"screening import: {preview.filename or 'run file'}",
            )
            if auto_created_batches > 0:
                resolutions = resolve_rows(
                    normalized.rows,
                    batch_index=batch_index,
                    compound_index=compound_index,
                    overrides=cmd.compound_batch_overrides,
                )

        # 6d. Re-validate the FE-provided picks. If anything is still
        # ambiguous after applying overrides, the chemist's submission
        # was incomplete; refuse the write.
        if resolutions.ambiguous_compounds:
            names = ", ".join(a.molecule_name for a in resolutions.ambiguous_compounds)
            return Failure(
                ValidationError(
                    f"Compound disambiguation required for: {names}. "
                    "Re-open the preview and pick a batch for each ambiguous compound."
                )
            )
        if resolutions.row_conflicts:
            joined = "\n  - ".join(
                f"{c.plate_name} {c.well_label}: {c.reason}"
                for c in resolutions.row_conflicts[:10]
            )
            tail = (
                f"\n  ... and {len(resolutions.row_conflicts) - 10} more"
                if len(resolutions.row_conflicts) > 10
                else ""
            )
            return Failure(
                ValidationError(f"Batch Ref / Compound Ref disagree on:\n  - {joined}{tail}")
            )

        # 7. Load existing readouts for the run; build the conflict scan.
        existing_readouts = await self._readout_data_repo.find_by_run(cmd.workspace_id, run.id)
        rd_name_by_id = {rd.id: rd.name for rd in protocol.readout_definitions}
        # Build allowed-label sets for each PICK_LIST readout def. The scan
        # uses these to flag rows whose value isn't in the set. None for
        # non-pick-list defs — they aren't constrained.
        pick_list_allowed: dict[uuid.UUID, set[str]] = {}
        for rd in protocol.readout_definitions:
            if rd.data_type == ReadoutDataType.PICK_LIST and rd.pick_list_values:
                pick_list_allowed[rd.id] = {v.label for v in rd.pick_list_values}

        plan = _scan_conflicts(
            normalized,
            run,
            existing_readouts,
            templates_by_format,
            resolutions=resolutions,
            rd_name_by_id=rd_name_by_id,
            pick_list_allowed=pick_list_allowed,
        )

        # 7b. Pick-list violations are hard errors — refuse to commit a
        # half-broken import. The wizard's preview pass would have caught
        # this with a real mapping, but we re-validate here for safety.
        if plan.pick_list_violations:
            return Failure(
                ValidationError(
                    "Pick-list constraint violations:\n  - "
                    + "\n  - ".join(plan.pick_list_violations[:10])
                    + (
                        f"\n  ... and {len(plan.pick_list_violations) - 10} more"
                        if len(plan.pick_list_violations) > 10
                        else ""
                    )
                )
            )

        # 8. Apply plan: create new plates, attach new wells, write new
        # readouts. Existing entities are reused as-is.
        result = ImportRunFileResult(
            rows_total=len(normalized.rows),
            skipped_rows=normalized.skipped_rows,
            conflicts_well_metadata=list(plan.well_conflicts),
            conflicts_readout=list(plan.readout_conflicts),
            controls_from_template=plan.controls_from_template,
            controls_unclassified=plan.controls_unclassified,
            unmatched_batches=sorted(resolutions.unmatched_batch_refs),
            unmatched_compound_refs=sorted(resolutions.unmatched_compound_refs),
            auto_created_batches=auto_created_batches,
        )

        # Track new plates first so we can emit creation counters.
        for new_plate in plan.new_plates:
            new_plate.wells = plan.wells_for_new_plate.get(  # type: ignore[attr-defined]
                new_plate.id, []
            )
            run.add_plate(new_plate)
            result.plates_created += 1
            result.wells_created += len(plan.wells_for_new_plate.get(new_plate.id, []))

        # Wells appended to existing plates: add directly to run.wells.
        for w in plan.new_wells_for_existing_plates:
            run.wells.append(w)
            result.wells_created += 1

        # The resolver has already attached molecule_id + batch_id to
        # each row; the conflict scan threaded those through into the
        # _ReadoutWrite records. Just forward them to ReadoutData.
        new_readouts: list[ReadoutData] = []
        for rd_write in plan.new_readouts:
            new_readouts.append(
                ReadoutData(
                    workspace_id=cmd.workspace_id,
                    run_id=run.id,
                    well_id=rd_write.well_id,
                    molecule_id=rd_write.molecule_id,
                    batch_id=rd_write.batch_id,
                    readout_definition_id=rd_write.readout_definition_id,
                    value=rd_write.value,
                    value_text=rd_write.value_text,
                )
            )

        await self._run_repo.save(run)
        if new_readouts:
            await self._readout_data_repo.save_bulk(new_readouts)
            result.readouts_created = len(new_readouts)

        await self._uow.commit()
        return Success(result)

    async def _maybe_run_calc_engine(
        self, cmd: ImportRunFileCommand, result: ImportRunFileResult
    ) -> None:
        if self._calc_engine is None:
            return
        compute_result = await self._calc_engine.compute_for_run(
            run_id=cmd.run_id, workspace_id=cmd.workspace_id
        )
        if isinstance(compute_result, Failure):
            result.compute_warning = str(compute_result.failure())
        else:
            result.fit_warnings = list(compute_result.unwrap().fit_warnings)

    async def _maybe_attach_raw_file(
        self,
        cmd: ImportRunFileCommand,
        preview: _StoredPreview,
        result: ImportRunFileResult,
        auth: AuthContext | None,
    ) -> None:
        """Persist the raw uploaded file as a Run attachment.

        The Files tab is the audit log of what was uploaded for the run.
        We attach on every successful import — including the no-op case
        where the file was fully redundant — because the chemist's
        intent ("this file represents this run's source data") is
        independent of how many cells actually changed.
        """
        if auth is None:
            result.attachment_warning = "no auth context — skipped"
            return
        upload_cmd = UploadAttachmentCommand(
            workspace_id=cmd.workspace_id,
            attachable_type=AttachableType.RUN,
            attachable_id=cmd.run_id,
            uploaded_by=auth.user_id,
            file_name=preview.filename or f"run-import-{cmd.preview_id}.bin",
            mime_type=preview.content_type,
            file_data=preview.raw_bytes,
        )
        try:
            attach_result = await self._upload_attachment(upload_cmd, auth=auth)
        except Exception as exc:
            result.attachment_warning = f"attachment failed: {exc}"
            _log.warning(
                "run_import.attachment_failed",
                run_id=str(cmd.run_id),
                workspace_id=str(cmd.workspace_id),
                file_name=upload_cmd.file_name,
                error=str(exc),
                exc_info=True,
            )
            return
        if isinstance(attach_result, Failure):
            result.attachment_warning = str(attach_result.failure())
        else:
            result.attachment_id = attach_result.unwrap().id


# Suppress unused-import warnings for re-exports that exist solely to
# preserve the original public surface of this module. The names are
# part of ``__all__`` above.
_ = (
    _guess_content_type,
    AmbiguousCompoundDTO,
    BatchOption,
    PlatePreview,
    PreviewRunFileQuery,
    PreviewRunFileResult,
    RepreviewRunFileQuery,
    InMemoryPreviewStore,
)
