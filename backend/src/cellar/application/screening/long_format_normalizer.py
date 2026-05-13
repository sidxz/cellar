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

Well-type classification is NOT done here — the importer derives WellType
from the protocol's configured ``control_layouts`` (PlateTemplate.template_map)
since the file format itself can't distinguish positive from negative controls.
"""

from __future__ import annotations

import re
import uuid
from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Literal

from returns.result import Failure, Result, Success

from cellar.application.shared.parsers import ParsedTable
from cellar.domain.shared.enums import PlateFormat
from cellar.domain.shared.errors import DomainError, ValidationError

# ---------------------------------------------------------------------------
# Roles + confidence
# ---------------------------------------------------------------------------

Role = Literal[
    "well",
    "plate_name",
    "concentration",
    "batch_ref",
    "compound_ref",
    "readout",
]

Confidence = Literal["high", "medium", "low"]

ReadoutValueKind = Literal["numeric", "text"]


# ---------------------------------------------------------------------------
# Mapping types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ReadoutColumn:
    """A header that produces readout values bound to a readout definition.

    ``data_type`` controls how cells are parsed: ``"numeric"`` runs the
    standard float parse; ``"text"`` keeps the stripped raw string.
    """

    header: str
    readout_definition_id: uuid.UUID
    data_type: ReadoutValueKind = "numeric"


@dataclass(frozen=True)
class ColumnMapping:
    """Resolved column-role mapping used by ``normalize``.

    ``batch_ref`` and ``compound_ref`` may both be set when a file
    carries both kinds of column. Per-row precedence is applied later
    by the compound-ref resolver, not here.
    """

    well: str
    plate_name: str | None = None
    concentration: str | None = None
    batch_ref: str | None = None
    compound_ref: str | None = None
    readout_columns: tuple[ReadoutColumn, ...] = ()


@dataclass(frozen=True)
class ReadoutDefRef:
    """Lightweight reference to a protocol's readout definition.

    Passed into ``infer_mapping`` so that headers whose name matches a
    protocol-defined readout (e.g. a Text readout named "Scientist") are
    suggested as ``role="readout"`` with ``confidence="high"`` and the
    matching def id pre-bound — without coupling the normalizer module to
    the full domain ReadoutDefinition aggregate.
    """

    id: uuid.UUID
    name: str
    data_type: str  # "numeric" | "text" | "dose_response" | "pick_list"


@dataclass(frozen=True)
class HeaderSuggestion:
    """One suggested role for a single header.

    ``readout_definition_id`` is set only when the inference step decided
    that this header maps to a specific protocol-defined readout (exact
    name match against the ``readout_defs`` argument to ``infer_mapping``).
    The wizard uses it to pre-bind the readout-def select.
    """

    header: str
    role: Role | None
    confidence: Confidence
    reason: str = ""
    readout_definition_id: uuid.UUID | None = None


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
    compound_ref: str | None
    concentration: float | None
    readouts: dict[uuid.UUID, float | str]


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
                "lgcy batch name",
            )
        ]
    ),
    "compound_ref": frozenset(
        [
            _norm(x)
            for x in (
                "compound",
                "compound id",
                "compound name",
                "molecule",
                "molecule id",
                "molecule name",
                "synonym",
                "external id",
                "registration number",
                "reg number",
                "cv id",
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


def infer_mapping(
    table: ParsedTable,
    sample_size: int = 100,
    readout_defs: Sequence[ReadoutDefRef] = (),
) -> SuggestedMapping:
    """Suggest a role for each header, with confidence.

    Inference stages (highest to lowest precedence):
      1. **Synonym dictionary** — header matches a built-in synonym for a
         core role (well / plate_name / concentration / batch_ref).
         Confidence: high.
      2. **Readout-definition name match** — header (after normalization)
         exactly equals the name of a protocol-defined readout def.
         Confidence: high. The matching def's id is attached to the
         suggestion so the wizard can pre-bind the readout-def select.
         Only ``numeric`` and ``text`` readout defs are considered;
         ``dose_response`` and ``pick_list`` are computed/derived and
         shouldn't be column-mapped.
      3. **Value-based fallback** — heuristics on cell values:
         - >80% match ``[A-Z]{1,2}\\d{1,2}`` → ``well``.
         - Numeric, high uniqueness, no nulls → ``readout`` (low/medium).
         - Numeric with many repeats and many nulls → ``concentration``.
         - Long string with shared prefix → ``plate_name``.
         - Short string ID-shaped → ``batch_ref``.

    Synonym precedence over readout-def name match guards against a
    protocol that smuggled a reserved well-metadata name (e.g. a readout
    def named "concentration") into its catalog — the synonym still wins,
    and the user can manually re-bind if the readout def really was
    intended.

    Each role can be claimed by multiple headers; ``ColumnMapping`` then
    picks the user-confirmed assignment. Readout columns may be multiple
    by design.
    """
    sample_rows = list(table.rows[:sample_size])
    suggestions: list[HeaderSuggestion] = []
    role_taken: dict[Role, bool] = {}

    # Build a normalized-name index for protocol-defined readouts.
    bindable_defs: dict[str, ReadoutDefRef] = {
        _norm(d.name): d for d in readout_defs if d.data_type in ("numeric", "text")
    }

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

        # 2. Readout-definition name match
        bound_def = bindable_defs.get(norm)
        if bound_def is not None:
            suggestions.append(
                HeaderSuggestion(
                    header=header,
                    role="readout",
                    confidence="high",
                    reason=f'header matches readout def "{bound_def.name}"',
                    readout_definition_id=bound_def.id,
                )
            )
            continue

        # 3. Value-based fallback
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

    Returns ``Failure(ValidationError)`` if the well column header is not
    present on the table or if no valid rows are produced.
    """
    if mapping.well not in table.headers:
        return Failure(ValidationError(f"Well column '{mapping.well}' not found in file headers"))
    for col in (
        mapping.plate_name,
        mapping.concentration,
        mapping.batch_ref,
        mapping.compound_ref,
    ):
        if col is not None and col not in table.headers:
            return Failure(ValidationError(f"Column '{col}' not found in file headers"))
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
            (raw.get(mapping.plate_name) or "").strip() if mapping.plate_name else "Plate-1"
        )
        if not plate_name:
            plate_name = "Plate-1"

        batch_ref = (
            (raw.get(mapping.batch_ref) or "").strip() if mapping.batch_ref else ""
        ) or None
        compound_ref = (
            (raw.get(mapping.compound_ref) or "").strip() if mapping.compound_ref else ""
        ) or None

        conc = _parse_float(raw.get(mapping.concentration)) if mapping.concentration else None

        readouts: dict[uuid.UUID, float | str] = {}
        for rc in mapping.readout_columns:
            cell = raw.get(rc.header)
            if rc.data_type == "text":
                if cell is None:
                    continue
                text = str(cell).strip()
                if not text:
                    continue
                readouts[rc.readout_definition_id] = text
            else:
                v = _parse_float(cell)
                if v is not None:
                    readouts[rc.readout_definition_id] = v

        rows.append(
            LongFormatRow(
                plate_name=plate_name,
                well=parsed_well,
                batch_ref=batch_ref,
                compound_ref=compound_ref,
                concentration=conc,
                readouts=readouts,
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
