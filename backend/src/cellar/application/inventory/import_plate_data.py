"""3-phase plate data import pipeline (industry-standard)."""

from __future__ import annotations

import csv
import io
import uuid
from dataclasses import dataclass, field
from datetime import date
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

from returns.result import Failure, Result, Success

from cellar.application.auth import require_editor, require_workspace_role
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.inventory.import_template import ImportTemplate
from cellar.domain.inventory.repository import BatchRepository, RegisteredPlateRepository
from cellar.domain.shared.errors import DomainError, ValidationError

if TYPE_CHECKING:
    from cellar.application.auth import AuthContext
    from cellar.application.screening.bulk_create_readout_data import BulkCreateReadoutData
    from cellar.application.screening.create_run import CreateRun


# ---------------------------------------------------------------------------
# Phase 1: Preview
# ---------------------------------------------------------------------------


@dataclass
class ImportPreview:
    file_id: str
    filename: str
    headers: list[str]
    preview_rows: list[list[str]]
    row_count: int
    suggested_template_id: str | None = None
    suggested_template_name: str | None = None


@runtime_checkable
class ImportFileCache(Protocol):
    """Application-layer port for caching uploaded import files between
    preview / validate / execute steps.

    The default in-memory implementation lives in
    ``infrastructure/cache/in_memory_file_cache.py`` and is bound via DI.
    Application code depends on this Protocol so the storage backend
    (in-memory, Valkey, etc.) is an infrastructure concern.
    """

    def put(
        self,
        workspace_id: uuid.UUID,
        file_id: str,
        headers: list[str],
        data_rows: list[list[str]],
    ) -> None: ...

    def get(
        self, workspace_id: uuid.UUID, file_id: str
    ) -> tuple[list[str], list[list[str]]] | None: ...

    def pop(
        self, workspace_id: uuid.UUID, file_id: str
    ) -> tuple[list[str], list[list[str]]] | None: ...

    def contains(self, workspace_id: uuid.UUID, file_id: str) -> bool: ...


def preview_import_file(
    filename: str, content: bytes, cache: ImportFileCache, *, workspace_id: uuid.UUID
) -> Result[ImportPreview, DomainError]:
    """Parse CSV/TSV, cache content, return preview."""
    file_id = str(uuid.uuid4())

    # Detect delimiter
    text = content.decode("utf-8-sig")
    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",\t")
    except csv.Error:
        dialect = csv.excel  # type: ignore[assignment]

    reader = csv.reader(io.StringIO(text), dialect)
    rows = list(reader)

    if len(rows) < 1:
        return Failure(ValidationError("File is empty"))

    headers = rows[0]
    data_rows = rows[1:]

    cache.put(workspace_id, file_id, headers, data_rows)

    return Success(
        ImportPreview(
            file_id=file_id,
            filename=filename,
            headers=headers,
            preview_rows=data_rows[:10],
            row_count=len(data_rows),
        )
    )


def auto_match_template(
    headers: list[str],
    templates: list[ImportTemplate],
) -> tuple[str | None, str | None]:
    """Match file headers against saved templates by header name overlap.

    Compares file header names against each template's column_mappings keys.
    Returns ``(template_id, template_name)`` when the best match reaches ≥90%
    coverage, otherwise ``(None, None)``.
    """
    best_score = 0.0
    best_template: ImportTemplate | None = None

    file_headers = set(headers)

    for tpl in templates:
        tpl_headers = set(tpl.column_mappings.keys())
        if not tpl_headers:
            continue
        matched = len(tpl_headers & file_headers)
        score = matched / len(tpl_headers)
        if score > best_score:
            best_score = score
            best_template = tpl

    if best_template is not None and best_score >= 0.9:
        return str(best_template.id), best_template.name
    return None, None


# ---------------------------------------------------------------------------
# Phase 2 + 3: Service
# ---------------------------------------------------------------------------


@dataclass
class ValidationDetail:
    row: int
    issue: str
    severity: str  # "error" or "warning"


@dataclass
class ValidationResult:
    total_rows: int
    matched: int
    unresolved: int
    errors: int
    details: list[ValidationDetail] = field(default_factory=list)


@dataclass
class ImportExecutionResult:
    imported_count: int
    skipped_count: int
    readout_count: int = 0
    errors: list[str] = field(default_factory=list)


class ImportPlateDataService:
    """Orchestrates phases 2 (validate) and 3 (execute) of the import pipeline."""

    def __init__(
        self,
        uow: UnitOfWork,
        plate_repo: RegisteredPlateRepository,
        batch_repo: BatchRepository,
        cache: ImportFileCache,
        create_run: CreateRun | None = None,
        bulk_create_readout_data: BulkCreateReadoutData | None = None,
    ) -> None:
        self._uow = uow
        self._plate_repo = plate_repo
        self._batch_repo = batch_repo
        self._cache = cache
        self._create_run = create_run
        self._bulk_create = bulk_create_readout_data

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _find_column_indices(
        headers: list[str],
        column_mappings: dict[str, str],
    ) -> tuple[int | None, int | None]:
        """Return (barcode_idx, well_idx) from column_mappings.

        column_mappings may be keyed by header name *or* by column index str.
        """
        barcode_idx: int | None = None
        well_idx: int | None = None

        for idx, header in enumerate(headers):
            # Accept both "header_name" and "0", "1", ... as keys
            target = column_mappings.get(header) or column_mappings.get(str(idx))
            if target == "plate_barcode":
                barcode_idx = idx
            elif target == "well_position":
                well_idx = idx

        return barcode_idx, well_idx

    @staticmethod
    def _find_readout_indices(
        headers: list[str],
        column_mappings: dict[str, str],
    ) -> dict[int, str]:
        """Return {column_index: readout_definition_id} for readout-mapped columns."""
        readout_map: dict[int, str] = {}
        for idx, header in enumerate(headers):
            target = column_mappings.get(header) or column_mappings.get(str(idx))
            if target and target.startswith("readout:"):
                readout_def_id = target[len("readout:") :]
                readout_map[idx] = readout_def_id
        return readout_map

    @staticmethod
    def _find_qualifier_index(
        headers: list[str],
        column_mappings: dict[str, str],
    ) -> int | None:
        """Return column index for the qualifier column, if mapped."""
        for idx, header in enumerate(headers):
            target = column_mappings.get(header) or column_mappings.get(str(idx))
            if target == "qualifier":
                return idx
        return None

    # ------------------------------------------------------------------
    # Phase 2: Validate
    # ------------------------------------------------------------------

    async def validate(
        self,
        file_id: str,
        column_mappings: dict[str, str],
        workspace_id: uuid.UUID,
        auth: AuthContext | None = None,
    ) -> Result[ValidationResult, DomainError]:
        """Validate column mappings against cached data rows."""
        require_workspace_role(auth, "viewer")
        cached = self._cache.get(workspace_id, file_id)
        if cached is None:
            return Failure(
                ValidationError(f"File {file_id!r} not found in cache (expired or invalid)")
            )

        async with self._uow:
            headers, data_rows = cached
            barcode_idx, well_idx = self._find_column_indices(headers, column_mappings)

            details: list[ValidationDetail] = []
            matched = 0
            unresolved = 0
            error_count = 0

            for row_num, row in enumerate(data_rows, start=2):
                if barcode_idx is not None and barcode_idx < len(row):
                    barcode = row[barcode_idx].strip()
                    if not barcode:
                        matched += 1
                        continue

                    plate = await self._plate_repo.find_by_barcode(workspace_id, barcode)
                    if plate is None:
                        details.append(
                            ValidationDetail(
                                row=row_num,
                                issue=f"Plate {barcode!r} not found",
                                severity="error",
                            )
                        )
                        error_count += 1
                        unresolved += 1
                        continue

                    if well_idx is not None and well_idx < len(row):
                        well_pos = row[well_idx].strip().upper()
                        if well_pos and plate.well_map and well_pos not in plate.well_map:
                            details.append(
                                ValidationDetail(
                                    row=row_num,
                                    issue=f"Well {well_pos} not mapped on plate {barcode!r}",
                                    severity="warning",
                                )
                            )

                matched += 1

            return Success(
                ValidationResult(
                    total_rows=len(data_rows),
                    matched=matched,
                    unresolved=unresolved,
                    errors=error_count,
                    details=details[:100],
                )
            )

    # ------------------------------------------------------------------
    # Phase 3: Execute
    # ------------------------------------------------------------------

    async def execute(
        self,
        file_id: str,
        column_mappings: dict[str, str],
        workspace_id: uuid.UUID,
        protocol_id: uuid.UUID | None,
        run_id: uuid.UUID | None,
        auth: AuthContext | None = None,
    ) -> Result[ImportExecutionResult, DomainError]:
        """Execute import — resolve wells to batches/molecules, create ReadoutData.

        For each data row:
        - Resolve plate barcode → RegisteredPlate → well_map → batch_id
        - Resolve batch_id → molecule_id (via batch lookup)
        - Extract readout values from mapped columns
        - If protocol_id provided: auto-create Run if needed, then BulkCreateReadoutData
        """
        require_editor(auth)
        cached = self._cache.get(workspace_id, file_id)
        if cached is None:
            return Failure(
                ValidationError(f"File {file_id!r} not found in cache (expired or invalid)")
            )

        headers, data_rows = cached
        barcode_idx, well_idx = self._find_column_indices(headers, column_mappings)
        readout_indices = self._find_readout_indices(headers, column_mappings)
        qualifier_idx = self._find_qualifier_index(headers, column_mappings)

        # Phase 1: Resolve plate → well → batch → molecule (read-only)
        resolved_rows: list[dict[str, Any]] = []
        imported = 0
        skipped = 0
        errors: list[str] = []
        plate_cache: dict[str, Any] = {}

        async with self._uow:
            for row_num, row in enumerate(data_rows, start=2):
                try:
                    barcode = (
                        row[barcode_idx].strip()
                        if barcode_idx is not None and barcode_idx < len(row)
                        else None
                    )
                    well_pos = (
                        row[well_idx].strip().upper()
                        if well_idx is not None and well_idx < len(row)
                        else None
                    )

                    if not barcode or not well_pos:
                        skipped += 1
                        continue

                    if barcode not in plate_cache:
                        plate_cache[barcode] = await self._plate_repo.find_by_barcode(
                            workspace_id, barcode
                        )
                    plate = plate_cache[barcode]

                    if plate is None:
                        errors.append(f"Row {row_num}: Plate {barcode!r} not found")
                        skipped += 1
                        continue

                    well_map = plate.well_map if hasattr(plate, "well_map") else {}
                    well_entry = well_map.get(well_pos) if well_map else None

                    if not well_entry or not well_entry.get("batch_id"):
                        errors.append(
                            f"Row {row_num}: Well {well_pos} not mapped on plate {barcode!r}"
                        )
                        skipped += 1
                        continue

                    batch_id_raw = well_entry["batch_id"]
                    try:
                        batch_id = uuid.UUID(str(batch_id_raw))
                    except (ValueError, AttributeError):
                        errors.append(f"Row {row_num}: Invalid batch_id {batch_id_raw!r}")
                        skipped += 1
                        continue

                    batch = await self._batch_repo.find_by_id_in_workspace(workspace_id, batch_id)
                    if batch is None:
                        errors.append(f"Row {row_num}: Batch {batch_id} not found")
                        skipped += 1
                        continue

                    # Extract readout values from this row
                    row_readouts: dict[str, tuple[float | None, str | None]] = {}
                    qualifier = None
                    if qualifier_idx is not None and qualifier_idx < len(row):
                        qualifier = row[qualifier_idx].strip() or None

                    for col_idx, readout_def_id in readout_indices.items():
                        if col_idx < len(row):
                            raw_val = row[col_idx].strip()
                            if raw_val:
                                try:
                                    row_readouts[readout_def_id] = (float(raw_val), qualifier)
                                except ValueError:
                                    row_readouts[readout_def_id] = (None, raw_val)

                    resolved_rows.append(
                        {
                            "molecule_id": batch.molecule_id,
                            "batch_id": batch_id,
                            "readouts": row_readouts,
                        }
                    )
                    imported += 1

                except (IndexError, ValueError, AttributeError) as exc:
                    errors.append(f"Row {row_num}: {exc}")
                    skipped += 1

        # Phase 2: Create ReadoutData if protocol + readout columns present
        readout_count = 0
        if (
            protocol_id
            and readout_indices
            and resolved_rows
            and self._create_run
            and self._bulk_create
        ):
            readout_count = await self._create_readout_data(
                workspace_id=workspace_id,
                protocol_id=protocol_id,
                run_id=run_id,
                resolved_rows=resolved_rows,
                auth=auth,
                errors=errors,
            )

        # Pop the cached file only after the full import (including readout
        # creation) completes — that way a failure in Phase 2 leaves the
        # cached file intact so the client can retry without re-uploading.
        self._cache.pop(workspace_id, file_id)

        return Success(
            ImportExecutionResult(
                imported_count=imported,
                skipped_count=skipped,
                readout_count=readout_count,
                errors=errors[:50],
            )
        )

    async def _create_readout_data(
        self,
        workspace_id: uuid.UUID,
        protocol_id: uuid.UUID,
        run_id: uuid.UUID | None,
        resolved_rows: list[dict[str, Any]],
        auth: AuthContext | None,
        errors: list[str],
    ) -> int:
        """Auto-create Run (if needed) and bulk-insert ReadoutData."""
        from cellar.application.screening.bulk_create_readout_data import (
            BulkCreateReadoutDataCommand,
            ReadoutDataItem,
        )
        from cellar.application.screening.create_run import CreateRunCommand

        # Auto-create a Run if none provided
        if run_id is None:
            if self._create_run is None:
                errors.append("CreateRun service not configured for plate import")
                return 0
            run_result = await self._create_run(
                CreateRunCommand(
                    workspace_id=workspace_id,
                    protocol_id=protocol_id,
                    run_date=date.today(),
                    notes="Auto-created from plate data import",
                ),
                auth=auth,
            )
            if isinstance(run_result, Failure):
                errors.append(f"Failed to create run: {run_result.failure()}")
                return 0
            run_id = run_result.unwrap().id

        # Build ReadoutDataItem list
        items: list[ReadoutDataItem] = []
        for row_data in resolved_rows:
            for readout_def_id, (value_numeric, qualifier) in row_data["readouts"].items():
                items.append(
                    ReadoutDataItem(
                        run_id=run_id,
                        molecule_id=row_data["molecule_id"],
                        batch_id=row_data["batch_id"],
                        readout_definition_id=uuid.UUID(readout_def_id),
                        value_numeric=value_numeric,
                        value_qualifier=qualifier,
                        value_text=None if value_numeric is not None else qualifier,
                    )
                )

        if not items:
            return 0

        if self._bulk_create is None:
            errors.append("BulkCreateReadoutData service not configured for plate import")
            return 0
        bulk_result = await self._bulk_create(
            BulkCreateReadoutDataCommand(
                workspace_id=workspace_id,
                items=items,
            ),
            auth=auth,
        )
        if isinstance(bulk_result, Failure):
            errors.append(f"ReadoutData creation failed: {bulk_result.failure()}")
            return 0

        result = bulk_result.unwrap()
        if result.errors:
            for err in result.errors[:10]:
                errors.append(f"ReadoutData error: {err}")
        return result.success_count
