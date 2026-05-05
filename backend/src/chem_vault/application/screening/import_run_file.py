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
    infer_mapping,
    normalize,
)
from chem_vault.application.shared.command import Command
from chem_vault.application.shared.event_dispatcher import EventDispatcherProtocol
from chem_vault.application.shared.unit_of_work import UnitOfWork
from chem_vault.domain.inventory.repository import BatchRepository
from chem_vault.domain.screening_assay.enums import WellType
from chem_vault.domain.screening_assay.readout_data import ReadoutData
from chem_vault.domain.screening_assay.repository import (
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
    controls_inferred: int = 0
    skipped_rows: int = 0


# ---------------------------------------------------------------------------
# PreviewRunFile use case
# ---------------------------------------------------------------------------


class PreviewRunFile:
    """Parse + suggest mapping + dry-resolve batches; cache for import."""

    def __init__(
        self,
        run_repo: RunRepository,
        batch_repo: BatchRepository,
        preview_store: PreviewStore,
    ) -> None:
        self._run_repo = run_repo
        self._batch_repo = batch_repo
        self._store = preview_store

    async def __call__(
        self,
        input: PreviewRunFileQuery,
        auth: AuthContext | None = None,
    ) -> Result[PreviewRunFileResult, DomainError]:
        try:
            require_editor(auth)
        except DomainError as exc:
            return Failure(exc)

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
                    norm.rows, input.workspace_id, self._batch_repo
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
        preview_store: PreviewStore,
        dispatcher: EventDispatcherProtocol | None = None,
    ) -> None:
        self._uow = uow
        self._run_repo = run_repo
        self._protocol_repo = protocol_repo
        self._readout_data_repo = readout_data_repo
        self._batch_repo = batch_repo
        self._store = preview_store
        self._dispatcher = dispatcher

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

        # 6. Resolve batch references
        batch_lookup = await _build_batch_lookup(
            normalized.rows, cmd.workspace_id, self._batch_repo
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

            well_type = row.inferred_well_type
            if well_type == WellType.BLANK:
                result.controls_inferred += 1

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
                sample_count=sum(1 for r in plate_rows if r.inferred_well_type == WellType.SAMPLE),
                blank_count=sum(1 for r in plate_rows if r.inferred_well_type == WellType.BLANK),
            )
        )
    return tuple(out)


async def _resolve_batches(
    rows: Iterable[LongFormatRow],
    workspace_id: uuid.UUID,
    batch_repo: BatchRepository,
) -> tuple[int, set[str]]:
    matched = 0
    unmatched: set[str] = set()
    seen: set[str] = set()
    for r in rows:
        if not r.batch_ref or r.batch_ref in seen:
            continue
        seen.add(r.batch_ref)
        batch = await batch_repo.find_by_batch_number(workspace_id, r.batch_ref)
        if batch is None:
            unmatched.add(r.batch_ref)
        else:
            matched += 1
    return matched, unmatched


async def _build_batch_lookup(
    rows: Iterable[LongFormatRow],
    workspace_id: uuid.UUID,
    batch_repo: BatchRepository,
) -> dict[str, tuple[uuid.UUID, uuid.UUID]]:
    """Return ``{batch_ref: (batch_id, molecule_id)}`` for refs that resolve."""
    out: dict[str, tuple[uuid.UUID, uuid.UUID]] = {}
    seen: set[str] = set()
    for r in rows:
        if not r.batch_ref or r.batch_ref in seen:
            continue
        seen.add(r.batch_ref)
        batch = await batch_repo.find_by_batch_number(workspace_id, r.batch_ref)
        if batch is not None:
            out[r.batch_ref] = (batch.id, batch.molecule_id)
    return out
