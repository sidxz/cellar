"""3-phase plate data import pipeline (CDD-style)."""

from __future__ import annotations

import csv
import io
import uuid
from dataclasses import dataclass, field

from chem_vault.domain.inventory.repository import RegisteredPlateRepository


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


# In-memory file cache (simple dict, keyed by file_id)
_file_cache: dict[str, tuple[str, list[str], list[list[str]]]] = {}


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

    # Cache headers + all data rows for validation/execution phases
    _file_cache[file_id] = (filename, headers, data_rows)

    return ImportPreview(
        file_id=file_id,
        filename=filename,
        headers=headers,
        preview_rows=data_rows[:10],
        row_count=len(data_rows),
    )


# ---------------------------------------------------------------------------
# Phase 2: Validate
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


async def validate_import_mapping(
    file_id: str,
    column_mappings: dict[str, str],
    protocol_id: uuid.UUID,
    run_id: uuid.UUID,
    plate_repo: RegisteredPlateRepository,
    workspace_id: uuid.UUID,
) -> ValidationResult:
    """Validate column mappings against actual data.

    column_mappings maps header_name -> target_field (e.g. "Barcode" -> "plate_barcode").
    """
    if file_id not in _file_cache:
        raise ValueError(f"File {file_id!r} not found in cache (expired or invalid)")

    _, headers, data_rows = _file_cache[file_id]

    # Build a header-name -> column-index lookup
    header_index: dict[str, int] = {h: i for i, h in enumerate(headers)}

    # Find which header maps to plate_barcode
    barcode_header: str | None = None
    for header, target in column_mappings.items():
        if target == "plate_barcode":
            barcode_header = header
            break

    details: list[ValidationDetail] = []
    matched = 0
    unresolved = 0
    error_count = 0

    for row_idx, row in enumerate(data_rows, start=2):  # 1-indexed + header row
        if barcode_header is not None:
            col_idx = header_index.get(barcode_header)
            barcode_value: str | None = None
            if col_idx is not None and col_idx < len(row):
                barcode_value = row[col_idx].strip() or None

            if barcode_value:
                plate = await plate_repo.find_by_barcode(workspace_id, barcode_value)
                if plate is None:
                    details.append(
                        ValidationDetail(
                            row=row_idx,
                            issue=f"Plate {barcode_value!r} not found",
                            severity="error",
                        )
                    )
                    error_count += 1
                    unresolved += 1
                    continue
            else:
                details.append(
                    ValidationDetail(
                        row=row_idx,
                        issue="Missing plate barcode",
                        severity="warning",
                    )
                )

        matched += 1

    return ValidationResult(
        total_rows=len(data_rows),
        matched=matched,
        unresolved=unresolved,
        errors=error_count,
        details=details[:50],  # Limit detail output
    )


# ---------------------------------------------------------------------------
# Phase 3: Execute
# ---------------------------------------------------------------------------


@dataclass
class ImportExecutionResult:
    imported_count: int
    skipped_count: int
    errors: list[str] = field(default_factory=list)


async def execute_import(
    file_id: str,
    column_mappings: dict[str, str],
    protocol_id: uuid.UUID,
    run_id: uuid.UUID,
    workspace_id: uuid.UUID,
) -> ImportExecutionResult:
    """Execute the import — create ReadoutData records.

    NOTE: Full integration with BulkCreateReadoutData will be wired
    when the import is connected end-to-end. For now, this validates
    the file is still cached and returns a placeholder result.
    The actual ReadoutData creation requires the screening context's
    BulkCreateReadoutData use case which will be injected at the route level.
    """
    if file_id not in _file_cache:
        raise ValueError(f"File {file_id!r} not found in cache (expired or invalid)")

    _, _headers, data_rows = _file_cache[file_id]

    # Clean up cache after execution
    del _file_cache[file_id]

    return ImportExecutionResult(
        imported_count=len(data_rows),
        skipped_count=0,
    )


def clear_file_cache(file_id: str) -> None:
    """Remove a file from the in-memory cache."""
    _file_cache.pop(file_id, None)
