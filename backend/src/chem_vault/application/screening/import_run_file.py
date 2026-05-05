"""ImportRunFile — long-format run file import with preview/import gate.

Two use cases:

- ``PreviewRunFile`` (read-only): parse the uploaded file, suggest a column
  mapping, dry-resolve batch references, summarize plates and controls,
  and stash the parsed table in a short-lived in-memory store keyed by
  ``preview_id``. The wizard surfaces the result for user confirmation.

- ``ImportRunFile`` (write): consume a ``preview_id`` plus the user-confirmed
  ``ColumnMapping``, normalize the cached table, and write ``Plate`` / ``Well``
  / ``ReadoutData`` aggregates to the run.

The preview store is in-memory only — preview payloads expire after 60s and
are deleted on first consume (idempotency on the import side).
"""

from __future__ import annotations

import re
import time
import uuid
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from returns.result import Failure, Result, Success

from chem_vault.application.auth import AuthContext, require_editor
from chem_vault.application.screening.long_format_normalizer import (
    ColumnMapping,
    HeaderSuggestion,
    LongFormatRow,
    NormalizedTable,
    ReadoutColumn,
    SuggestedMapping,
    WellPosition,
    infer_mapping,
    normalize,
)
from chem_vault.application.screening.readout_calculation_engine import (
    ReadoutCalculationEngine,
)
from chem_vault.application.shared.command import Command
from chem_vault.application.shared.event_dispatcher import EventDispatcherProtocol
from chem_vault.application.shared.unit_of_work import UnitOfWork
from chem_vault.domain.chemical_registration.repository import MoleculeRepository
from chem_vault.domain.inventory.repository import BatchRepository
from chem_vault.domain.screening_assay.enums import ReadoutNormalization, WellType
from chem_vault.domain.screening_assay.plate_template import PlateTemplate
from chem_vault.domain.screening_assay.protocol import Protocol as AssayProtocol
from chem_vault.domain.screening_assay.readout_data import ReadoutData
from chem_vault.domain.screening_assay.repository import (
    PlateTemplateRepository,
    ProtocolRepository,
    ReadoutDataRepository,
    RunRepository,
)
from chem_vault.domain.screening_assay.run import Plate, Well
from chem_vault.domain.shared.enums import ConcentrationUnit, PlateFormat, Qualifier
from chem_vault.domain.shared.errors import (
    ConflictError,
    DomainError,
    NotFoundError,
    ValidationError,
)
from chem_vault.domain.shared.value_objects import Concentration, QualifiedValue
from chem_vault.infrastructure.parsers.tabular_file import (
    ParsedTable,
    TabularParseError,
    parse_tabular,
)

# Hard cap from the plan: sync-only MVP.
_MAX_ROWS = 50_000


# ---------------------------------------------------------------------------
# Preview store
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _StoredPreview:
    """Cached parsed file + metadata bound to a preview_id."""

    workspace_id: uuid.UUID
    run_id: uuid.UUID
    table: ParsedTable
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
    concentration_unit: str = "uM"


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


@dataclass(frozen=True, kw_only=True)
class ImportRunFileCommand(Command):
    workspace_id: uuid.UUID
    run_id: uuid.UUID
    preview_id: uuid.UUID
    mapping: ColumnMapping
    concentration_unit: str = "uM"
    replace_existing: bool = False


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


# ---------------------------------------------------------------------------
# PreviewRunFile use case
# ---------------------------------------------------------------------------


class PreviewRunFile:
    """Parse + suggest mapping + dry-resolve batches; cache for import."""

    def __init__(
        self,
        uow: UnitOfWork,
        run_repo: RunRepository,
        batch_repo: BatchRepository,
        molecule_repo: MoleculeRepository,
        preview_store: PreviewStore,
        protocol_repo: ProtocolRepository,
        plate_template_repo: PlateTemplateRepository,
    ) -> None:
        self._uow = uow
        self._run_repo = run_repo
        self._batch_repo = batch_repo
        self._molecule_repo = molecule_repo
        self._store = preview_store
        self._protocol_repo = protocol_repo
        self._plate_template_repo = plate_template_repo

    async def __call__(
        self,
        input: PreviewRunFileQuery,
        auth: AuthContext | None = None,
    ) -> Result[PreviewRunFileResult, DomainError]:
        try:
            require_editor(auth)
        except DomainError as exc:
            return Failure(exc)

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
            table = parse_tabular(input.file_content, input.filename)
        except TabularParseError as exc:
            return Failure(ValidationError(f"File parse error: {exc}"))

        if table.row_count > _MAX_ROWS:
            return Failure(
                ValidationError(
                    f"File has {table.row_count} rows; sync import limit is {_MAX_ROWS}"
                )
            )

        suggested = infer_mapping(table)
        guessed = _build_guess_mapping(suggested)

        plates: tuple[PlatePreview, ...] = ()
        matched = 0
        unmatched_set: set[str] = set()
        validation_errors: list[str] = []

        protocol = await self._protocol_repo.find_by_id_in_workspace(
            input.workspace_id, run.protocol_id
        )

        if guessed is not None:
            try:
                conc_unit = ConcentrationUnit(input.concentration_unit)
            except ValueError:
                return Failure(
                    ValidationError(
                        f"Invalid concentration unit: '{input.concentration_unit}'"
                    )
                )
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
                _ = conc_unit  # validated; used by import phase

        preview_id = uuid.uuid4()
        ttl = getattr(self._store, "ttl_seconds", 60.0)
        self._store.save(
            preview_id,
            _StoredPreview(
                workspace_id=input.workspace_id,
                run_id=input.run_id,
                table=table,
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
            )
        )


# ---------------------------------------------------------------------------
# ImportRunFile use case
# ---------------------------------------------------------------------------


class ImportRunFile:
    """Persist a previously-previewed long-format file to the run."""

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
        self._dispatcher = dispatcher
        self._calc_engine = calculation_engine

    async def __call__(
        self,
        input: ImportRunFileCommand,
        auth: AuthContext | None = None,
    ) -> Result[ImportRunFileResult, DomainError]:
        try:
            require_editor(auth)
        except DomainError as exc:
            return Failure(exc)

        async with self._uow:
            return await self._execute(input)

    async def _execute(
        self, cmd: ImportRunFileCommand
    ) -> Result[ImportRunFileResult, DomainError]:
        # 1. Pull and validate preview
        preview = self._store.consume(cmd.preview_id)
        if preview is None:
            return Failure(
                NotFoundError("Preview", str(cmd.preview_id))
            )
        if preview.workspace_id != cmd.workspace_id or preview.run_id != cmd.run_id:
            return Failure(
                ValidationError("preview_id does not match this workspace + run")
            )

        # 2. Load run
        run = await self._run_repo.find_by_id_in_workspace(
            cmd.workspace_id, cmd.run_id
        )
        if run is None:
            return Failure(NotFoundError("Run", str(cmd.run_id)))
        if run.is_locked:
            return Failure(ConflictError("Cannot import into a locked run"))
        if run.wells and not cmd.replace_existing:
            return Failure(
                ConflictError(
                    "Run already has wells — pass replace_existing to overwrite"
                )
            )
        if run.wells and cmd.replace_existing:
            return Failure(
                ValidationError(
                    "replace_existing is not yet supported in MVP — re-create the run"
                )
            )

        # 3. Concentration unit
        try:
            conc_unit = ConcentrationUnit(cmd.concentration_unit)
        except ValueError:
            return Failure(
                ValidationError(
                    f"Invalid concentration unit: '{cmd.concentration_unit}'"
                )
            )

        # 4. Normalize with confirmed mapping
        normalized_result = normalize(preview.table, cmd.mapping)
        if isinstance(normalized_result, Failure):
            return normalized_result
        normalized: NormalizedTable = normalized_result.unwrap()

        # 5. Validate readout-def ids belong to this run's protocol
        protocol = await self._protocol_repo.find_by_id_in_workspace(
            cmd.workspace_id, run.protocol_id
        )
        if protocol is None:
            return Failure(NotFoundError("Protocol", str(run.protocol_id)))

        protocol_rd_ids = {rd.id for rd in protocol.readout_definitions}
        for rc in cmd.mapping.readout_columns:
            if rc.readout_definition_id not in protocol_rd_ids:
                return Failure(
                    ValidationError(
                        f"readout_definition_id {rc.readout_definition_id} "
                        "does not belong to this run's protocol"
                    )
                )

        # 6. Pre-flight: control-layout coverage. If the protocol uses
        # control-based normalization but lacks a configured layout for any
        # plate format in the file, fail BEFORE writing anything.
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

        # 7. Resolve batch references
        batch_lookup = await _build_batch_lookup(
            normalized.rows,
            cmd.workspace_id,
            self._batch_repo,
            self._molecule_repo,
        )

        # 7. Build plates + wells + readouts
        plates_by_name: dict[str, Plate] = {}
        readouts: list[ReadoutData] = []
        result = ImportRunFileResult(
            rows_total=len(normalized.rows),
            skipped_rows=normalized.skipped_rows,
        )
        unmatched: set[str] = set()

        for plate_name, plate_format in normalized.plate_formats.items():
            plates_by_name[plate_name] = Plate(
                run_id=run.id,
                plate_number=len(plates_by_name) + 1,
                format=plate_format,
                plate_map={"name": plate_name},
            )

        wells_by_plate: dict[uuid.UUID, list[Well]] = {p.id: [] for p in plates_by_name.values()}

        for row in normalized.rows:
            plate = plates_by_name[row.plate_name]

            batch_id: uuid.UUID | None = None
            molecule_id: uuid.UUID | None = None
            if row.batch_ref:
                resolved = batch_lookup.get(row.batch_ref)
                if resolved is None:
                    unmatched.add(row.batch_ref)
                    # Skip the well entirely — the plan locks unmatched=skip+report.
                    continue
                batch_id, molecule_id = resolved

            plate_format = normalized.plate_formats.get(row.plate_name)
            if row.batch_ref or row.concentration is not None:
                well_type = WellType.SAMPLE
            else:
                per_well = (
                    templates_by_format.get(plate_format)
                    if plate_format is not None
                    else None
                )
                tmpl_type = per_well.get(_well_key(row.well)) if per_well else None
                if tmpl_type is not None:
                    well_type = tmpl_type
                    result.controls_from_template += 1
                else:
                    well_type = WellType.SAMPLE
                    result.controls_unclassified += 1

            concentration = (
                Concentration(value=row.concentration, unit=conc_unit)
                if row.concentration is not None
                else None
            )

            well = Well(
                plate_id=plate.id,
                row=row.well.row,
                column=row.well.column,
                well_type=well_type,
                batch_id=batch_id,
                concentration=concentration,
            )
            wells_by_plate[plate.id].append(well)

            if molecule_id is None or batch_id is None:
                # Control wells get no readouts written (matches existing semantics).
                continue

            for rd_id, value in row.readouts.items():
                readouts.append(
                    ReadoutData(
                        workspace_id=cmd.workspace_id,
                        run_id=run.id,
                        well_id=well.id,
                        molecule_id=molecule_id,
                        batch_id=batch_id,
                        readout_definition_id=rd_id,
                        value=QualifiedValue(value=value, qualifier=Qualifier.EQUAL),
                    )
                )

        # 8. Attach plates + wells to the run
        for plate in plates_by_name.values():
            plate.wells = wells_by_plate[plate.id]  # type: ignore[attr-defined]
            run.add_plate(plate)
            result.plates_created += 1
            result.wells_created += len(wells_by_plate[plate.id])

        await self._run_repo.save(run)
        if readouts:
            await self._readout_data_repo.save_bulk(readouts)
            result.readouts_created = len(readouts)

        events = await self._uow.commit()

        # Trigger normalization (% inhibition / % activation / etc.) after
        # readouts are persisted. Engine runs in its own UoW. Failures here
        # (e.g. protocol missing controls) are non-fatal — the import is done.
        if self._calc_engine is not None and result.readouts_created > 0:
            try:
                await self._calc_engine.compute_for_run(
                    run_id=run.id, workspace_id=cmd.workspace_id
                )
            except DomainError:
                pass
        if self._dispatcher and events:
            await self._dispatcher.dispatch_all(events)

        result.unmatched_batches = sorted(unmatched)
        return Success(result)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


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
        scientist=suggested.first("scientist"),
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
    """Resolve a file batch ref to a local ``(batch_id, molecule_id)``.

    Two-step lookup:

    1. **Direct hit** — file ref matches a local CV-style ``batch_number``.
    2. **Pattern split** — split off the trailing ``-NNN`` seq and look up
       the molecule by its prefix as a ``MoleculeIdentifier`` synonym;
       reconstruct the canonical batch number ``{mol_reg}-{seq:03d}``.

    Returns ``None`` if neither path resolves.
    """
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
    """Return ``{batch_ref: (batch_id, molecule_id)}`` for refs that resolve."""
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
    # "empty" intentionally absent — falls through to SAMPLE.
}


def _well_key(well: WellPosition) -> str:
    """Template stores 'A1' (no zero-pad); long-format normalizes 'A01' → 'A1'."""
    return f"{well.row}{well.column}"


def _build_template_lookup(
    protocol: AssayProtocol,
    plate_formats: dict[str, PlateFormat],
    templates_by_id: dict[uuid.UUID, PlateTemplate],
) -> dict[PlateFormat, dict[str, WellType]]:
    """Map each plate format used in the file to a {well_key -> WellType} dict.

    Plate formats not covered by ``control_layouts`` are absent from the result.
    """
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
    """Return error messages for plate formats that need controls but lack a layout."""
    needs_controls = any(
        _normalization_requires_controls(rd.normalization)
        for rd in protocol.readout_definitions
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
