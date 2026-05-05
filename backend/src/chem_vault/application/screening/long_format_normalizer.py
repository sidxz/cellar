"""Long-format run file normalizer.

Pure functions that convert a generic ``ParsedTable`` (rows of plate name +
well + concentration + batch ref + readout values) into typed
``LongFormatRow`` records ready for persistence by ``ImportRunFile``.

This module contains no I/O. It does:

  1. Synonym + value-based **header role inference** (``infer_mapping``).
  2. **Normalization** of parsed rows to typed values
     (``normalize``), including:
       - well-position canonicalization (``A01`` ↔ ``A1``)
       - per-plate format inference (96 / 384 / 1536)
       - control-well inference (``BLANK`` when value present but batch absent)
"""

from __future__ import annotations

import re
import uuid
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Literal

from returns.result import Failure, Result, Success

from chem_vault.domain.screening_assay.enums import WellType
from chem_vault.domain.shared.enums import PlateFormat
from chem_vault.domain.shared.errors import DomainError, ValidationError
from chem_vault.infrastructure.parsers.tabular_file import ParsedTable

# ---------------------------------------------------------------------------
# Roles + confidence
# ---------------------------------------------------------------------------

Role = Literal[
    "well",
    "plate_name",
    "concentration",
    "batch_ref",
    "scientist",
    "readout",
]

Confidence = Literal["high", "medium", "low"]


# ---------------------------------------------------------------------------
# Mapping types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ReadoutColumn:
    """A header that produces readout values bound to a readout definition."""

    header: str
    readout_definition_id: uuid.UUID


@dataclass(frozen=True)
class ColumnMapping:
    """Resolved column-role mapping used by ``normalize``."""

    well: str
    plate_name: str | None = None
    concentration: str | None = None
    batch_ref: str | None = None
    scientist: str | None = None
    readout_columns: tuple[ReadoutColumn, ...] = ()


@dataclass(frozen=True)
class HeaderSuggestion:
    """One suggested role for a single header."""

    header: str
    role: Role | None
    confidence: Confidence
    reason: str = ""


@dataclass(frozen=True)
class SuggestedMapping:
    """Output of ``infer_mapping`` — one suggestion per source header."""

    suggestions: tuple[HeaderSuggestion, ...]

    def by_role(self, role: Role) -> list[HeaderSuggestion]:
        return [s for s in self.suggestions if s.role == role]

    def first(self, role: Role) -> str | None:
        matches = self.by_role(role)
        return matches[0].header if matches else None


# ---------------------------------------------------------------------------
# Normalized output
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class WellPosition:
    """Canonical well position — single-letter row + 1-based column."""

    row: str
    column: int

    @property
    def label(self) -> str:
        return f"{self.row}{self.column:02d}"


@dataclass(frozen=True)
class LongFormatRow:
    """One normalized row from a long-format run file."""

    plate_name: str
    well: WellPosition
    batch_ref: str | None
    concentration: float | None
    readouts: dict[uuid.UUID, float]
    scientist: str | None
    inferred_well_type: WellType


@dataclass(frozen=True)
class NormalizedTable:
    """Full output of ``normalize``."""

    rows: tuple[LongFormatRow, ...]
    plate_formats: dict[str, PlateFormat]
    skipped_rows: int = 0


# ---------------------------------------------------------------------------
# Synonym dictionary
# ---------------------------------------------------------------------------


def _norm(s: str) -> str:
    """Lowercase + strip non-alphanumeric — used for header matching."""
    return re.sub(r"[^a-z0-9]+", "", s.lower())


_SYNONYMS: dict[Role, frozenset[str]] = {
    "well": frozenset(
        [_norm(x) for x in ("well", "position", "address", "wellid", "well position")]
    ),
    "plate_name": frozenset(
        [
            _norm(x)
            for x in (
                "plate",
                "plate name",
                "plate id",
                "plate barcode",
                "barcode",
            )
        ]
    ),
    "concentration": frozenset(
        [
            _norm(x)
            for x in (
                "concentration",
                "conc",
                "dose",
                "conc um",
                "conc nm",
                "conc mm",
                "concentration um",
                "c",
            )
        ]
    ),
    "batch_ref": frozenset(
        [
            _norm(x)
            for x in (
                "batch",
                "batch id",
                "batch name",
                "lot",
                "lot number",
                "sample id",
                "compound id",
                "lgcy batch name",
            )
        ]
    ),
    "scientist": frozenset(
        [
            _norm(x)
            for x in (
                "scientist",
                "operator",
                "user",
                "performed by",
                "analyst",
            )
        ]
    ),
    "readout": frozenset(
        [
            _norm(x)
            for x in (
                "value",
                "raw data",
                "raw",
                "signal",
                "absorbance",
                "fluorescence",
                "luminescence",
                "ic50",
                "percent inhibition",
                "% inhibition",
                "inhibition",
            )
        ]
    ),
}


_WELL_RE = re.compile(r"^[A-Z]{1,2}\d{1,2}$", re.IGNORECASE)


# ---------------------------------------------------------------------------
# Public API — infer_mapping
# ---------------------------------------------------------------------------


def infer_mapping(table: ParsedTable, sample_size: int = 100) -> SuggestedMapping:
    """Suggest a role for each header, with confidence.

    1. Synonym dictionary (high confidence on hit).
    2. Value-based fallback for unknowns:
        - >80% of sampled cells match ``[A-Z]{1,2}\\d{1,2}`` → ``well``.
        - Numeric, high uniqueness, no nulls → ``readout``.
        - Numeric with many repeats and many nulls → ``concentration``.
        - Long string with shared prefix → ``plate_name``.
        - Short string ID-shaped (mixed alnum + dashes) → ``batch_ref``.

    Each role can be claimed by multiple headers; ``ColumnMapping`` then picks
    the user-confirmed assignment. Readout columns may be multiple by design.
    """
    sample_rows = list(table.rows[:sample_size])
    suggestions: list[HeaderSuggestion] = []
    role_taken: dict[Role, bool] = {}

    for header in table.headers:
        norm = _norm(header)
        # 1. Synonym match
        role = _synonym_role(norm)
        if role is not None:
            allow_dup = role == "readout"
            if allow_dup or not role_taken.get(role):
                suggestions.append(
                    HeaderSuggestion(
                        header=header,
                        role=role,
                        confidence="high",
                        reason="header matched synonym dictionary",
                    )
                )
                role_taken[role] = True
                continue

        # 2. Value-based fallback
        values = [(r.get(header) or "").strip() for r in sample_rows]
        guess, conf, reason = _guess_role_from_values(values, role_taken)
        suggestions.append(
            HeaderSuggestion(header=header, role=guess, confidence=conf, reason=reason)
        )
        if guess is not None and guess != "readout":
            role_taken[guess] = True

    return SuggestedMapping(suggestions=tuple(suggestions))


def _synonym_role(norm_header: str) -> Role | None:
    for role, syns in _SYNONYMS.items():
        if norm_header in syns:
            return role
    return None


def _guess_role_from_values(
    values: list[str], role_taken: dict[Role, bool]
) -> tuple[Role | None, Confidence, str]:
    non_empty = [v for v in values if v]
    if not non_empty:
        return None, "low", "column is empty"

    null_ratio = 1.0 - (len(non_empty) / max(len(values), 1))

    well_hits = sum(1 for v in non_empty if _WELL_RE.match(v))
    if well_hits / len(non_empty) > 0.8 and not role_taken.get("well"):
        return "well", "medium", "values look like well coordinates"

    numeric_hits = 0
    for v in non_empty:
        try:
            float(v)
            numeric_hits += 1
        except ValueError:
            pass
    numeric_ratio = numeric_hits / len(non_empty)

    if numeric_ratio > 0.95:
        unique = len({v for v in non_empty})
        unique_ratio = unique / len(non_empty)
        if null_ratio < 0.1 and unique_ratio > 0.5 and not role_taken.get("readout"):
            return "readout", "medium", "numeric, mostly distinct, few nulls"
        if null_ratio > 0.2 and unique <= 30 and not role_taken.get("concentration"):
            return "concentration", "medium", "numeric with repeats and nulls"

    # Strings — distinguish plate_name (long, shared prefix) vs batch_ref (id-shaped)
    string_hits = len(non_empty) - numeric_hits
    if string_hits / len(non_empty) > 0.8:
        if not role_taken.get("plate_name") and _has_shared_prefix(non_empty, min_len=8):
            return "plate_name", "low", "long strings share a prefix"
        if not role_taken.get("batch_ref") and any("-" in v for v in non_empty):
            return "batch_ref", "low", "values look like batch identifiers"

    return None, "low", "no confident role match"


def _has_shared_prefix(values: list[str], min_len: int) -> bool:
    if len(values) < 2:
        return False
    prefix = values[0]
    for v in values[1:]:
        i = 0
        while i < min(len(prefix), len(v)) and prefix[i] == v[i]:
            i += 1
        prefix = prefix[:i]
        if len(prefix) < min_len:
            return False
    return True


# ---------------------------------------------------------------------------
# Public API — normalize
# ---------------------------------------------------------------------------


def normalize(
    table: ParsedTable,
    mapping: ColumnMapping,
) -> Result[NormalizedTable, DomainError]:
    """Convert parsed rows + mapping to typed long-format rows.

    - Well positions are canonicalized to ``WellPosition(row, column)``.
    - Plate name comes from ``mapping.plate_name`` if set; otherwise all
      rows are assigned to a single synthetic plate ``"Plate-1"``.
    - Concentration is parsed as float; missing/invalid → ``None``.
    - Readouts are parsed per ``ReadoutColumn``; non-numeric cells are
      dropped silently from that row's readout dict.
    - Inferred well type: rows with at least one readout value but no
      batch_ref AND no concentration ⇒ ``BLANK``; otherwise ``SAMPLE``.

    Returns ``Failure(ValidationError)`` if the well column header is not
    present on the table or if no valid rows are produced.
    """
    if mapping.well not in table.headers:
        return Failure(
            ValidationError(f"Well column '{mapping.well}' not found in file headers")
        )
    for col in (mapping.plate_name, mapping.concentration, mapping.batch_ref, mapping.scientist):
        if col is not None and col not in table.headers:
            return Failure(
                ValidationError(f"Column '{col}' not found in file headers")
            )
    for rc in mapping.readout_columns:
        if rc.header not in table.headers:
            return Failure(
                ValidationError(f"Readout column '{rc.header}' not found in file headers")
            )

    rows: list[LongFormatRow] = []
    skipped = 0
    for raw in table.iter_rows():
        well_str = (raw.get(mapping.well) or "").strip()
        if not well_str:
            skipped += 1
            continue

        parsed_well = _parse_well(well_str)
        if parsed_well is None:
            skipped += 1
            continue

        plate_name = (
            (raw.get(mapping.plate_name) or "").strip()
            if mapping.plate_name
            else "Plate-1"
        )
        if not plate_name:
            plate_name = "Plate-1"

        batch_ref = (
            (raw.get(mapping.batch_ref) or "").strip() if mapping.batch_ref else ""
        ) or None

        conc = _parse_float(raw.get(mapping.concentration)) if mapping.concentration else None

        scientist = (
            (raw.get(mapping.scientist) or "").strip()
            if mapping.scientist
            else None
        ) or None

        readouts: dict[uuid.UUID, float] = {}
        for rc in mapping.readout_columns:
            v = _parse_float(raw.get(rc.header))
            if v is not None:
                readouts[rc.readout_definition_id] = v

        well_type = _infer_well_type(batch_ref, conc, readouts)

        rows.append(
            LongFormatRow(
                plate_name=plate_name,
                well=parsed_well,
                batch_ref=batch_ref,
                concentration=conc,
                readouts=readouts,
                scientist=scientist,
                inferred_well_type=well_type,
            )
        )

    if not rows:
        return Failure(ValidationError("No valid rows in file"))

    plate_formats = _infer_plate_formats(rows)
    return Success(
        NormalizedTable(
            rows=tuple(rows),
            plate_formats=plate_formats,
            skipped_rows=skipped,
        )
    )


def _parse_well(raw: str) -> WellPosition | None:
    """Parse 'A1', 'A01', 'AA12' → WellPosition. Returns None on failure."""
    s = raw.strip().upper()
    m = re.match(r"^([A-Z]{1,2})(\d{1,2})$", s)
    if not m:
        return None
    row = m.group(1)
    try:
        col = int(m.group(2))
    except ValueError:
        return None
    if col < 1 or col > 48:
        return None
    return WellPosition(row=row, column=col)


def _parse_float(raw: object) -> float | None:
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _infer_well_type(
    batch_ref: str | None,
    concentration: float | None,
    readouts: dict[uuid.UUID, float],
) -> WellType:
    if batch_ref or concentration is not None:
        return WellType.SAMPLE
    if readouts:
        return WellType.BLANK
    return WellType.SAMPLE


def _infer_plate_formats(rows: Iterable[LongFormatRow]) -> dict[str, PlateFormat]:
    """Infer the plate format per plate from its max well coordinates."""
    by_plate: dict[str, list[WellPosition]] = defaultdict(list)
    for r in rows:
        by_plate[r.plate_name].append(r.well)

    out: dict[str, PlateFormat] = {}
    for plate, wells in by_plate.items():
        max_col = max(w.column for w in wells)
        max_row = max(_row_index(w.row) for w in wells)
        out[plate] = _pick_format(max_row, max_col)
    return out


def _row_index(row: str) -> int:
    """A→1, B→2, ..., Z→26, AA→27, AB→28, ..."""
    n = 0
    for ch in row:
        n = n * 26 + (ord(ch) - ord("A") + 1)
    return n


_FORMAT_DIMS: tuple[tuple[PlateFormat, int, int], ...] = (
    (PlateFormat.F6, 2, 3),
    (PlateFormat.F12, 3, 4),
    (PlateFormat.F24, 4, 6),
    (PlateFormat.F48, 6, 8),
    (PlateFormat.F96, 8, 12),
    (PlateFormat.F384, 16, 24),
    (PlateFormat.F1536, 32, 48),
)


def _pick_format(max_row: int, max_col: int) -> PlateFormat:
    for fmt, rows, cols in _FORMAT_DIMS:
        if max_row <= rows and max_col <= cols:
            return fmt
    return PlateFormat.F1536
