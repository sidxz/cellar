"""DTOs for the summary-results import (wide-format endpoint values)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import StrEnum


class SummaryRole(StrEnum):
    COMPOUND_REF = "compound_ref"
    BATCH_REF = "batch_ref"
    READOUT = "readout"
    IGNORE = "ignore"


@dataclass(frozen=True, kw_only=True)
class SummaryHeaderSuggestion:
    header: str
    role: SummaryRole
    confidence: str  # "high" | "medium" | "low"
    readout_definition_id: uuid.UUID | None = None  # set when role==READOUT and a def name matched
    note: str = ""


@dataclass(frozen=True, kw_only=True)
class SummaryColumnMapping:
    """Confirmed mapping the chemist sends back on import."""

    compound_ref: str | None = None  # header providing registration numbers
    batch_ref: str | None = None  # header providing batch numbers
    # header -> readout_definition_id
    readout_columns: dict[str, uuid.UUID] = field(default_factory=dict)


@dataclass(frozen=True, kw_only=True)
class SummaryPreviewResult:
    headers: list[str]
    suggestions: list[SummaryHeaderSuggestion]
    sample_rows: list[dict[str, str]]  # first N rows, header->raw string
    total_rows: int
    matched_refs: int = 0  # rows whose compound/batch ref resolved (dry-run)
    unmatched_refs: list[str] = field(default_factory=list)
    validation_errors: list[str] = field(default_factory=list)


@dataclass(frozen=True, kw_only=True)
class SummaryImportPlanPreview:
    """Dry-run forecast of a summary import (resolve + insert/update), no writes."""

    total_rows: int
    matched_compound_count: int
    unmatched_compound_refs: list[str] = field(default_factory=list)
    unmatched_batch_refs: list[str] = field(default_factory=list)
    values_to_insert: int = 0
    values_to_update: int = 0
    rows_skipped: int = 0
    errors: list[dict[str, str]] = field(default_factory=list)


@dataclass(frozen=True, kw_only=True)
class SummaryImportResult:
    rows_processed: int = 0
    values_inserted: int = 0
    values_updated: int = 0
    rows_skipped: int = 0
    errors: list[dict[str, str]] = field(default_factory=list)
