"""ImportRunFile — long-format run file import with preview/import gate.

Two use cases:

- ``PreviewRunFile`` (read-only): parse the uploaded file, suggest a column
  mapping, dry-resolve batch references, summarize plates and controls,
  scan for conflicts against existing run state, and stash the parsed
  table + raw bytes in a short-lived in-memory store keyed by
  ``preview_id``. The wizard surfaces the result for user confirmation.

- ``ImportRunFile`` (write): consume a ``preview_id`` plus the
  user-confirmed ``ColumnMapping``. Re-runs the conflict scan as the
  source of truth, then writes only the non-conflicting plates, wells,
  and readouts. Conflicts are returned for reporting; nothing existing
  is overwritten. The raw uploaded bytes are persisted as a Run
  attachment on success so the file is part of the audit trail.

The preview store is in-memory only — preview payloads expire after 60s
and are deleted on first consume (idempotency on the import side).
"""

from __future__ import annotations

import re
import time
import uuid
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from returns.result import Failure, Result, Success

from chem_vault.application.attachment.upload_attachment import (
    UploadAttachment,
    UploadAttachmentCommand,
)
from chem_vault.application.auth import AuthContext, require_editor

# Re-exported here so existing callers `from import_run_file import WellConflict`
# keep working; the underscore-prefixed names are also re-imported for any
# tests/utilities that historically reached through this module.
from chem_vault.application.screening.import_plan import (  # noqa: F401
    ReadoutConflict,
    WellConflict,
    _ImportPlan,
    _ReadoutWrite,
    _scan_conflicts,
    _well_key,
    _well_metadata_mismatch,
)
from chem_vault.application.screening.long_format_normalizer import (
    ColumnMapping,
    HeaderSuggestion,
    LongFormatRow,
    NormalizedTable,
    ReadoutColumn,
    ReadoutDefRef,
    SuggestedMapping,
    infer_mapping,
    normalize,
)
from chem_vault.application.screening.readout_calculation_engine import (
    ReadoutCalculationEngine,
)
from chem_vault.application.shared.command import Command
from chem_vault.application.shared.event_dispatcher import EventDispatcherProtocol
from chem_vault.application.shared.parsers import (
    ParsedTable,
    TabularParseError,
    TabularParser,
)
from chem_vault.application.shared.unit_of_work import UnitOfWork
from chem_vault.domain.attachment.enums import AttachableType
from chem_vault.domain.chemical_registration.repository import MoleculeRepository
from chem_vault.domain.inventory.repository import BatchRepository
from chem_vault.domain.screening_assay.enums import (
    ReadoutDataType,
    ReadoutNormalization,
    WellType,
)
from chem_vault.domain.screening_assay.plate_template import PlateTemplate
from chem_vault.domain.screening_assay.protocol import Protocol as AssayProtocol
from chem_vault.domain.screening_assay.readout_data import ReadoutData
from chem_vault.domain.screening_assay.repository import (
    PlateTemplateRepository,
    ProtocolRepository,
    ReadoutDataRepository,
    RunRepository,
)
from chem_vault.domain.shared.enums import PlateFormat
from chem_vault.domain.shared.errors import (
    ConflictError,
    DomainError,
    NotFoundError,
    ValidationError,
)

# Hard cap from the plan: sync-only MVP.
_MAX_ROWS = 50_000


# ---------------------------------------------------------------------------
# Preview store
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _StoredPreview:
    """Cached parsed file + raw bytes bound to a preview_id.

    Raw bytes are kept so the importer can persist the original upload
    as a Run attachment after a successful write — the Files tab is
    the canonical audit log of what was uploaded for the run.
    """

    workspace_id: uuid.UUID
    run_id: uuid.UUID
    table: ParsedTable
    raw_bytes: bytes
    filename: str
    content_type: str
    expires_at: float


@runtime_checkable
class PreviewStore(Protocol):
    """Short-lived store for parsed preview tables."""

    def save(self, key: uuid.UUID, payload: _StoredPreview) -> None: ...
    def consume(self, key: uuid.UUID) -> _StoredPreview | None: ...


class InMemoryPreviewStore:
    """In-process preview store with TTL eviction. Single-process only."""

    def __init__(self, ttl_seconds: float = 60.0, *, clock=time.monotonic) -> None:
        self._items: dict[uuid.UUID, _StoredPreview] = {}
        self._ttl = ttl_seconds
        self._clock = clock

    @property
    def ttl_seconds(self) -> float:
        return self._ttl

    def save(self, key: uuid.UUID, payload: _StoredPreview) -> None:
        self._items[key] = payload

    def consume(self, key: uuid.UUID) -> _StoredPreview | None:
        self._evict_expired()
        return self._items.pop(key, None)

    def _evict_expired(self) -> None:
        now = self._clock()
        stale = [k for k, v in self._items.items() if v.expires_at <= now]
        for k in stale:
            del self._items[k]


# ---------------------------------------------------------------------------
# DTOs
# ---------------------------------------------------------------------------


@dataclass(frozen=True, kw_only=True)
class PreviewRunFileQuery(Command):
    workspace_id: uuid.UUID
    run_id: uuid.UUID
    file_content: bytes
    filename: str = ""
    content_type: str = ""


@dataclass(frozen=True)
class PlatePreview:
    plate_name: str
    plate_format: str
    well_count: int
    sample_count: int
    blank_count: int


@dataclass(frozen=True)
class PreviewRunFileResult:
    preview_id: uuid.UUID
    headers: tuple[str, ...]
    suggestions: tuple[HeaderSuggestion, ...]
    sample_rows: tuple[dict[str, str], ...]
    plates: tuple[PlatePreview, ...]
    matched_batches: int
    unmatched_batches: tuple[str, ...]
    total_rows: int
    expires_in_seconds: int
    validation_errors: tuple[str, ...] = ()
    will_create_plates: int = 0
    will_create_wells: int = 0
    will_create_readouts: int = 0
    will_skip_wells: tuple[WellConflict, ...] = ()
    will_skip_readouts: tuple[ReadoutConflict, ...] = ()


@dataclass(frozen=True, kw_only=True)
class ImportRunFileCommand(Command):
    workspace_id: uuid.UUID
    run_id: uuid.UUID
    preview_id: uuid.UUID
    mapping: ColumnMapping


@dataclass
class ImportRunFileResult:
    rows_total: int = 0
    plates_created: int = 0
    wells_created: int = 0
    readouts_created: int = 0
    unmatched_batches: list[str] = field(default_factory=list)
    controls_from_template: int = 0
    controls_unclassified: int = 0
    skipped_rows: int = 0
    conflicts_well_metadata: list[WellConflict] = field(default_factory=list)
    conflicts_readout: list[ReadoutConflict] = field(default_factory=list)
    attachment_id: uuid.UUID | None = None
    # Non-fatal warnings. ``compute_warning`` covers normalization /
    # aggregation failures (e.g. missing controls). ``attachment_warning``
    # covers attachment persistence failures — the import itself still
    # succeeded.
    compute_warning: str | None = None
    attachment_warning: str | None = None
    # Per-compound dose-response fit warnings surfaced from the calc engine.
    fit_warnings: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# PreviewRunFile use case
# ---------------------------------------------------------------------------


class PreviewRunFile:
    """Parse + suggest mapping + dry-resolve batches + scan conflicts."""

    def __init__(
        self,
        uow: UnitOfWork,
        run_repo: RunRepository,
        readout_data_repo: ReadoutDataRepository,
        batch_repo: BatchRepository,
        molecule_repo: MoleculeRepository,
        preview_store: PreviewStore,
        protocol_repo: ProtocolRepository,
        plate_template_repo: PlateTemplateRepository,
        parser: TabularParser,
    ) -> None:
        self._uow = uow
        self._run_repo = run_repo
        self._readout_data_repo = readout_data_repo
        self._batch_repo = batch_repo
        self._molecule_repo = molecule_repo
        self._store = preview_store
        self._protocol_repo = protocol_repo
        self._plate_template_repo = plate_template_repo
        self._parser = parser

    async def __call__(
        self,
        input: PreviewRunFileQuery,
        auth: AuthContext | None = None,
    ) -> Result[PreviewRunFileResult, DomainError]:
        require_editor(auth)

        async with self._uow:
            return await self._execute(input)

    async def _execute(
        self, input: PreviewRunFileQuery
    ) -> Result[PreviewRunFileResult, DomainError]:
        run = await self._run_repo.find_by_id_in_workspace(
            input.workspace_id, input.run_id
        )
        if run is None:
            return Failure(NotFoundError("Run", str(input.run_id)))

        try:
            table = self._parser.parse(input.file_content, input.filename)
        except TabularParseError as exc:
            return Failure(ValidationError(f"File parse error: {exc}"))

        if table.row_count > _MAX_ROWS:
            return Failure(
                ValidationError(
                    f"File has {table.row_count} rows; sync import limit is {_MAX_ROWS}"
                )
            )

        # Load the protocol first so its readout-definition catalog can
        # feed into infer_mapping. Headers whose name matches a defined
        # readout (e.g. a Text readout named "Scientist") are then
        # suggested as role=readout / confidence=high with the def id
        # attached — no FE-side upgrade or auto-binding needed.
        protocol = await self._protocol_repo.find_by_id_in_workspace(
            input.workspace_id, run.protocol_id
        )
        readout_def_refs: tuple[ReadoutDefRef, ...] = (
            tuple(
                ReadoutDefRef(
                    id=rd.id,
                    name=rd.name,
                    data_type=rd.data_type.value,
                )
                for rd in protocol.readout_definitions
            )
            if protocol is not None
            else ()
        )

        suggested = infer_mapping(table, readout_defs=readout_def_refs)
        guessed = _build_guess_mapping(suggested)

        plates: tuple[PlatePreview, ...] = ()
        matched = 0
        unmatched_set: set[str] = set()
        validation_errors: list[str] = []
        will_create_plates = 0
        will_create_wells = 0
        will_create_readouts = 0
        well_conflicts: list[WellConflict] = []
        readout_conflicts: list[ReadoutConflict] = []

        if guessed is not None:
            normalized = normalize(table, guessed)
            if isinstance(normalized, Success):
                norm: NormalizedTable = normalized.unwrap()
                plates = _summarize_plates(norm.rows, norm.plate_formats)
                matched, unmatched_set = await _resolve_batches(
                    norm.rows,
                    input.workspace_id,
                    self._batch_repo,
                    self._molecule_repo,
                )
                if protocol is not None:
                    templates_by_format = await _load_templates_by_format(
                        protocol,
                        norm.plate_formats,
                        input.workspace_id,
                        self._plate_template_repo,
                    )
                    validation_errors = _validate_controls_required(
                        protocol, norm.plate_formats, templates_by_format
                    )

                    # Conflict scan against existing run state. Uses a
                    # best-guess readout-def binding (each readout column
                    # maps to a fresh UUID in the guessed mapping, which
                    # is fine for plate/well-level counts; the readout
                    # cell-level scan is approximate at preview time and
                    # gets re-run authoritatively at import time once the
                    # user has bound real readout-def IDs).
                    existing_readouts = await self._readout_data_repo.find_by_run(
                        input.workspace_id, run.id
                    )
                    plan = _scan_conflicts(
                        norm,
                        run,
                        existing_readouts,
                        templates_by_format,
                    )
                    will_create_plates = plan.create_plate_count
                    will_create_wells = plan.create_well_count
                    will_create_readouts = plan.create_readout_count
                    well_conflicts = plan.well_conflicts
                    readout_conflicts = plan.readout_conflicts

        preview_id = uuid.uuid4()
        ttl = getattr(self._store, "ttl_seconds", 60.0)
        self._store.save(
            preview_id,
            _StoredPreview(
                workspace_id=input.workspace_id,
                run_id=input.run_id,
                table=table,
                raw_bytes=input.file_content,
                filename=input.filename,
                content_type=input.content_type or _guess_content_type(input.filename),
                expires_at=time.monotonic() + ttl,
            ),
        )

        sample = tuple(
            {h: (r.get(h) or "") for h in table.headers}
            for r in table.rows[:5]
        )

        return Success(
            PreviewRunFileResult(
                preview_id=preview_id,
                headers=tuple(table.headers),
                suggestions=suggested.suggestions,
                sample_rows=sample,
                plates=plates,
                matched_batches=matched,
                unmatched_batches=tuple(sorted(unmatched_set)),
                total_rows=table.row_count,
                expires_in_seconds=int(ttl),
                validation_errors=tuple(validation_errors),
                will_create_plates=will_create_plates,
                will_create_wells=will_create_wells,
                will_create_readouts=will_create_readouts,
                will_skip_wells=tuple(well_conflicts),
                will_skip_readouts=tuple(readout_conflicts),
            )
        )


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
            return Failure(
                ValidationError("preview_id does not match this workspace + run")
            )

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
        run = await self._run_repo.find_by_id_in_workspace(
            cmd.workspace_id, cmd.run_id
        )
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

        # 6. Resolve batch references.
        batch_lookup = await _build_batch_lookup(
            normalized.rows,
            cmd.workspace_id,
            self._batch_repo,
            self._molecule_repo,
        )

        # 7. Load existing readouts for the run; build the conflict scan.
        existing_readouts = await self._readout_data_repo.find_by_run(
            cmd.workspace_id, run.id
        )
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
            batch_lookup=batch_lookup,
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
            unmatched_batches=sorted(plan.unmatched_batches),
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

        # Resolve molecule_id for each new readout from the well's
        # batch -> molecule lookup. Wells can be brand new (so we use
        # batch_lookup directly) or existing (we read the well's
        # batch_id and look up the molecule via the existing batch).
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
        except Exception as exc:  # noqa: BLE001 — attachment is best-effort
            result.attachment_warning = f"attachment failed: {exc}"
            return
        if isinstance(attach_result, Failure):
            result.attachment_warning = str(attach_result.failure())
        else:
            result.attachment_id = attach_result.unwrap().id


# ---------------------------------------------------------------------------
# Conflict scanning helpers — see import_plan.py
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Helpers (parser + batch resolution + control layouts)
# ---------------------------------------------------------------------------


_CONTENT_TYPE_BY_EXT: dict[str, str] = {
    ".csv": "text/csv",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".xls": "application/vnd.ms-excel",
    ".tsv": "text/tab-separated-values",
}


def _guess_content_type(filename: str) -> str:
    if not filename:
        return "application/octet-stream"
    lower = filename.lower()
    for ext, ct in _CONTENT_TYPE_BY_EXT.items():
        if lower.endswith(ext):
            return ct
    return "application/octet-stream"


def _build_guess_mapping(suggested: SuggestedMapping) -> ColumnMapping | None:
    """Build a best-guess ColumnMapping from a SuggestedMapping.

    Used by the preview phase only — readout columns get throwaway UUIDs
    because preview cannot bind to real readout-definition ids.
    """
    well_header = suggested.first("well")
    if well_header is None:
        return None

    readouts = suggested.by_role("readout")
    return ColumnMapping(
        well=well_header,
        plate_name=suggested.first("plate_name"),
        concentration=suggested.first("concentration"),
        batch_ref=suggested.first("batch_ref"),
        readout_columns=tuple(
            ReadoutColumn(header=s.header, readout_definition_id=uuid.uuid4())
            for s in readouts
        ),
    )


def _summarize_plates(
    rows: Iterable[LongFormatRow],
    plate_formats: dict[str, PlateFormat],
) -> tuple[PlatePreview, ...]:
    by_plate: dict[str, list[LongFormatRow]] = {}
    for r in rows:
        by_plate.setdefault(r.plate_name, []).append(r)

    out: list[PlatePreview] = []
    for plate, plate_rows in sorted(by_plate.items()):
        out.append(
            PlatePreview(
                plate_name=plate,
                plate_format=plate_formats.get(plate, PlateFormat.F96).value,
                well_count=len(plate_rows),
                sample_count=sum(1 for r in plate_rows if r.batch_ref),
                blank_count=sum(1 for r in plate_rows if not r.batch_ref),
            )
        )
    return tuple(out)


# Trailing -NNN (1-3 digits) is treated as the local batch sequence.
_BATCH_REF_PATTERN = re.compile(r"^(?P<mol>.+)-(?P<seq>\d{1,3})$")


async def _resolve_batch_ref(
    batch_ref: str,
    workspace_id: uuid.UUID,
    batch_repo: BatchRepository,
    molecule_repo: MoleculeRepository,
) -> tuple[uuid.UUID, uuid.UUID] | None:
    direct = await batch_repo.find_by_batch_number(workspace_id, batch_ref)
    if direct is not None:
        return direct.id, direct.molecule_id

    m = _BATCH_REF_PATTERN.match(batch_ref)
    if m is None:
        return None
    mol_synonym = m.group("mol")
    seq = int(m.group("seq"))

    molecule = await molecule_repo.find_by_identifier(workspace_id, mol_synonym)
    if molecule is None:
        return None

    cv_batch_number = f"{molecule.registration_number.value}-{seq:03d}"
    batch = await batch_repo.find_by_batch_number(workspace_id, cv_batch_number)
    if batch is None:
        return None
    return batch.id, batch.molecule_id


async def _resolve_batches(
    rows: Iterable[LongFormatRow],
    workspace_id: uuid.UUID,
    batch_repo: BatchRepository,
    molecule_repo: MoleculeRepository,
) -> tuple[int, set[str]]:
    matched = 0
    unmatched: set[str] = set()
    seen: set[str] = set()
    for r in rows:
        if not r.batch_ref or r.batch_ref in seen:
            continue
        seen.add(r.batch_ref)
        resolved = await _resolve_batch_ref(
            r.batch_ref, workspace_id, batch_repo, molecule_repo
        )
        if resolved is None:
            unmatched.add(r.batch_ref)
        else:
            matched += 1
    return matched, unmatched


async def _build_batch_lookup(
    rows: Iterable[LongFormatRow],
    workspace_id: uuid.UUID,
    batch_repo: BatchRepository,
    molecule_repo: MoleculeRepository,
) -> dict[str, tuple[uuid.UUID, uuid.UUID]]:
    out: dict[str, tuple[uuid.UUID, uuid.UUID]] = {}
    seen: set[str] = set()
    for r in rows:
        if not r.batch_ref or r.batch_ref in seen:
            continue
        seen.add(r.batch_ref)
        resolved = await _resolve_batch_ref(
            r.batch_ref, workspace_id, batch_repo, molecule_repo
        )
        if resolved is not None:
            out[r.batch_ref] = resolved
    return out


# ---------------------------------------------------------------------------
# Control-layout helpers
# ---------------------------------------------------------------------------


_DESIGNATION_TO_WELL_TYPE: dict[str, WellType] = {
    "compound": WellType.SAMPLE,
    "positive_control": WellType.POSITIVE_CONTROL,
    "negative_control": WellType.NEGATIVE_CONTROL,
    "blank": WellType.BLANK,
}


def _build_template_lookup(
    protocol: AssayProtocol,
    plate_formats: dict[str, PlateFormat],
    templates_by_id: dict[uuid.UUID, PlateTemplate],
) -> dict[PlateFormat, dict[str, WellType]]:
    out: dict[PlateFormat, dict[str, WellType]] = {}
    for fmt in set(plate_formats.values()):
        tmpl_id = protocol.control_layouts.get(fmt.value)
        if tmpl_id is None:
            continue
        tmpl = templates_by_id.get(tmpl_id)
        if tmpl is None:
            continue
        per_well: dict[str, WellType] = {}
        for well_key, designation in (tmpl.template_map or {}).items():
            wt = _DESIGNATION_TO_WELL_TYPE.get(str(designation))
            if wt is not None:
                per_well[str(well_key)] = wt
        out[fmt] = per_well
    return out


async def _load_templates_by_format(
    protocol: AssayProtocol,
    plate_formats: dict[str, PlateFormat],
    workspace_id: uuid.UUID,
    plate_template_repo: PlateTemplateRepository,
) -> dict[PlateFormat, dict[str, WellType]]:
    used_fmts = set(plate_formats.values())
    templates_by_id: dict[uuid.UUID, PlateTemplate] = {}
    for fmt in used_fmts:
        tmpl_id = protocol.control_layouts.get(fmt.value)
        if tmpl_id is None or tmpl_id in templates_by_id:
            continue
        tmpl = await plate_template_repo.find_by_id_in_workspace(workspace_id, tmpl_id)
        if tmpl is not None:
            templates_by_id[tmpl_id] = tmpl
    return _build_template_lookup(protocol, plate_formats, templates_by_id)


def _normalization_requires_controls(rd_normalization: ReadoutNormalization) -> bool:
    return rd_normalization in (
        ReadoutNormalization.PERCENT_INHIBITION,
        ReadoutNormalization.PERCENT_ACTIVATION,
        ReadoutNormalization.PERCENT_CONTROL,
        ReadoutNormalization.Z_SCORE,
    )


def _validate_controls_required(
    protocol: AssayProtocol,
    plate_formats: dict[str, PlateFormat],
    templates: dict[PlateFormat, dict[str, WellType]],
) -> list[str]:
    needs_controls = any(
        _normalization_requires_controls(n)
        for rd in protocol.readout_definitions
        for n in rd.normalizations
    )
    if not needs_controls:
        return []
    errors: list[str] = []
    seen_formats: set[PlateFormat] = set()
    for fmt in plate_formats.values():
        if fmt in seen_formats:
            continue
        seen_formats.add(fmt)
        per_well = templates.get(fmt)
        if not per_well:
            errors.append(
                f"Protocol uses control-based normalization but no Control Layout "
                f"is configured for {fmt.value}-well plates. Configure one on the "
                f"protocol's Design tab."
            )
    return errors
