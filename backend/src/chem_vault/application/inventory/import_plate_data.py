"""3-phase plate data import pipeline (CDD-style)."""

from __future__ import annotations

import csv
import io
import uuid
from dataclasses import dataclass, field

from chem_vault.domain.inventory.import_template import ImportTemplate
from chem_vault.domain.inventory.repository import BatchRepository, RegisteredPlateRepository


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


# In-memory file cache — keyed by file_id, stores (headers, data_rows)
_file_cache: dict[str, tuple[list[str], list[list[str]]]] = {}


def preview_import_file(filename: str, content: bytes) -> ImportPreview:
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
        raise ValueError("File is empty")

    headers = rows[0]
    data_rows = rows[1:]

    # Cache (headers, data_rows) — both phases need the full content
    _file_cache[file_id] = (headers, data_rows)

    return ImportPreview(
        file_id=file_id,
        filename=filename,
        headers=headers,
        preview_rows=data_rows[:10],
        row_count=len(data_rows),
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
    errors: list[str] = field(default_factory=list)


class ImportPlateDataService:
    """Orchestrates phases 2 (validate) and 3 (execute) of the import pipeline."""

    def __init__(
        self,
        plate_repo: RegisteredPlateRepository,
        batch_repo: BatchRepository,
    ) -> None:
        self._plate_repo = plate_repo
        self._batch_repo = batch_repo

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

    # ------------------------------------------------------------------
    # Phase 2: Validate
    # ------------------------------------------------------------------

    async def validate(
        self,
        file_id: str,
        column_mappings: dict[str, str],
        workspace_id: uuid.UUID,
    ) -> ValidationResult:
        """Validate column mappings against cached data rows.

        Checks that every plate barcode resolves to a RegisteredPlate and,
        when a well_position column is mapped, that the well exists in the
        plate's well_map.
        """
        if file_id not in _file_cache:
            raise ValueError(f"File {file_id!r} not found in cache (expired or invalid)")

        headers, data_rows = _file_cache[file_id]
        barcode_idx, well_idx = self._find_column_indices(headers, column_mappings)

        details: list[ValidationDetail] = []
        matched = 0
        unresolved = 0
        error_count = 0

        for row_num, row in enumerate(data_rows, start=2):  # 1-indexed + header row
            if barcode_idx is not None and barcode_idx < len(row):
                barcode = row[barcode_idx].strip()
                if not barcode:
                    details.append(
                        ValidationDetail(
                            row=row_num,
                            issue="Missing plate barcode",
                            severity="warning",
                        )
                    )
                    matched += 1  # Not a hard error — row still counts
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

                # Validate well position if mapped
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

        return ValidationResult(
            total_rows=len(data_rows),
            matched=matched,
            unresolved=unresolved,
            errors=error_count,
            details=details[:100],
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
    ) -> ImportExecutionResult:
        """Execute import — resolve wells to batches/molecules.

        For each data row:
        - Resolve plate barcode → RegisteredPlate → well_map → batch_id
        - Resolve batch_id → molecule_id (via batch lookup)
        - Count as imported when both lookups succeed

        ReadoutData creation via BulkCreateReadoutData will be wired in a
        follow-up session when the screening-context integration is complete.
        """
        if file_id not in _file_cache:
            raise ValueError(f"File {file_id!r} not found in cache (expired or invalid)")

        headers, data_rows = _file_cache[file_id]
        barcode_idx, well_idx = self._find_column_indices(headers, column_mappings)

        imported = 0
        skipped = 0
        errors: list[str] = []

        # Plate cache to avoid repeated DB lookups for the same barcode
        plate_cache: dict[str, object] = {}

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

                # Resolve plate (cached)
                if barcode not in plate_cache:
                    plate_cache[barcode] = await self._plate_repo.find_by_barcode(
                        workspace_id, barcode
                    )
                plate = plate_cache[barcode]

                if plate is None:
                    errors.append(f"Row {row_num}: Plate {barcode!r} not found")
                    skipped += 1
                    continue

                # Resolve batch_id from well_map
                well_map = plate.well_map if hasattr(plate, "well_map") else {}  # type: ignore[union-attr]
                well_entry = well_map.get(well_pos) if well_map else None

                if not well_entry or not well_entry.get("batch_id"):
                    errors.append(
                        f"Row {row_num}: Well {well_pos} not mapped on plate {barcode!r}"
                    )
                    skipped += 1
                    continue

                # Resolve batch → molecule_id
                batch_id_raw = well_entry["batch_id"]
                try:
                    batch_id = uuid.UUID(str(batch_id_raw))
                except (ValueError, AttributeError):
                    errors.append(f"Row {row_num}: Invalid batch_id {batch_id_raw!r}")
                    skipped += 1
                    continue

                batch = await self._batch_repo.find_by_id(batch_id)
                if batch is None:
                    errors.append(f"Row {row_num}: Batch {batch_id} not found")
                    skipped += 1
                    continue

                # All lookups succeeded — plate → well → batch → molecule resolved
                # ReadoutData creation will be wired here via BulkCreateReadoutData
                # once the screening-context integration session is complete.
                imported += 1

            except (IndexError, ValueError, AttributeError) as exc:
                errors.append(f"Row {row_num}: {exc}")
                skipped += 1

        # Clean up cache after a successful execution pass
        del _file_cache[file_id]

        return ImportExecutionResult(
            imported_count=imported,
            skipped_count=skipped,
            errors=errors[:50],
        )


def clear_file_cache(file_id: str) -> None:
    """Remove a file from the in-memory cache."""
    _file_cache.pop(file_id, None)
