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

Well roles: when the file carries a role column ("Control State", "Well
Type", …) and it is mapped, each row's ``well_role`` is read from it and the
importer writes that role. Otherwise ``well_role`` stays ``None`` and the
importer derives WellType from the protocol's ``control_layouts``
(PlateTemplate.template_map).
"""

from __future__ import annotations

import math
import re
import uuid
from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Literal

from returns.result import Failure, Result, Success

from cellar.application.shared.parsers import ParsedTable
from cellar.domain.shared.enums import PlateFormat, WellType
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
    "well_role",
]

Confidence = Literal["high", "medium", "low"]

ReadoutValueKind = Literal["numeric", "text"]

# The note on a column the source platform calculated from the raw readout.
CALCULATED_BY_SOURCE = "Calculated by the source — Cellar calculates its own"


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
    # The file's per-well role column; when set it decides every well's role.
    well_role: str | None = None


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
    # The readout's normalization layers ("percent_inhibition", …).
    normalizations: tuple[str, ...] = ()
    # Computed by Cellar (formula / temperature window) — never imported.
    derived: bool = False


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
    # From the mapped role column (empty cell = sample). None when no role
    # column is mapped, or the cell holds a value we do not know.
    well_role: WellType | None = None


@dataclass(frozen=True)
class NormalizedTable:
    """Full output of ``normalize``."""

    rows: tuple[LongFormatRow, ...]
    plate_formats: dict[str, PlateFormat]
    skipped_rows: int = 0
    # Role-column values no WellType matches — the import refuses until they
    # are fixed (never read as samples). First spelling of each, in file order.
    unknown_well_roles: tuple[str, ...] = ()
    # The mapped role column's header; None = roles come from the layouts.
    well_role_column: str | None = None


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
    "well_role": frozenset(
        [_norm(x) for x in ("control state", "well type", "well role", "control")]
    ),
}

# Role-column values, compared after ``_norm``. Empty = a sample.
_WELL_ROLE_VALUES: dict[str, WellType] = {
    _norm(k): v
    for k, v in (
        ("", WellType.SAMPLE),
        ("sample", WellType.SAMPLE),
        ("compound", WellType.SAMPLE),
        ("negative control", WellType.NEGATIVE_CONTROL),
        ("positive control", WellType.POSITIVE_CONTROL),
        ("positive control (hit)", WellType.POSITIVE_CONTROL),
        ("reference", WellType.REFERENCE),
        ("reference molecule", WellType.REFERENCE),
        ("blank", WellType.BLANK),
    )
}


def unknown_well_roles_message(header: str, values: Sequence[str]) -> str:
    listed = ", ".join(f'"{v}"' for v in values)
    return (
        f'Unknown values in the "{header}" column: {listed}. Use negative control, '
        "positive control, reference or blank, or leave the cell empty for a sample."
    )


_WELL_RE = re.compile(r"^[A-Z]{1,2}\d{1,2}$", re.IGNORECASE)
_DATE_RE = re.compile(r"^\d{1,4}[-/.]\d{1,2}[-/.]\d{1,4}(?:[ T].*)?$")

# Headers of a normalized-percent column, per normalization a readout applies.
_NORMALIZED_HEADERS: dict[str, tuple[str, ...]] = {
    n: tuple(_norm(h) for h in headers)
    for n, headers in (
        ("percent_inhibition", ("percent inhibition", "% inhibition")),
        ("percent_activation", ("percent activation", "% activation")),
        ("percent_control", ("percent control", "percent of control", "% of control")),
        ("z_score", ("z score",)),
    )
}
# Curve-fit statistics a source reports next to a dose-response readout.
_CURVE_STATISTICS = frozenset(
    _norm(x)
    for x in (
        "curve class",
        "hill slope",
        "r squared",
        "r2",
        "span",
        "top",
        "bottom",
        "baseline response",
        "maximum response",
        "minimum response",
        "area under the curve",
        "auc",
        "n",
    )
)
_CURVE_STATISTIC_PREFIXES = (_norm("maximum measured"), _norm("minimum measured"))
# Plate QC the source computed (Cellar computes its own plate QC).
_PLATE_STATISTIC_SUFFIXES = (_norm("z'-factor"), _norm("z prime"))


# ---------------------------------------------------------------------------
# Public API — infer_mapping
# ---------------------------------------------------------------------------


def infer_mapping(
    table: ParsedTable,
    sample_size: int = 100,
    readout_defs: Sequence[ReadoutDefRef] = (),
) -> SuggestedMapping:
    """Suggest a role for each header, with confidence.

    Inference stages (highest to lowest precedence); a trailing unit in
    parentheses is ignored when matching names ("raw AU (AU)" = "raw AU"):
      1. **Synonym dictionary** — header matches a built-in synonym for a
         core role (well / plate_name / concentration / batch_ref /
         compound_ref / well_role), claimed across all headers before any
         value guess. Confidence: high.
      2. **Readout-definition name match** — header (after normalization)
         equals the name of a protocol-defined readout def.
         Confidence: high. The matching def's id is attached to the
         suggestion so the wizard can pre-bind the readout-def select.
         Only ``numeric`` and ``text`` readout defs are considered;
         ``dose_response`` and ``pick_list`` are computed/derived and
         shouldn't be column-mapped.
      3. **Calculated by the source** — a column the source derived from a
         raw readout Cellar normalizes or fits itself (% inhibition, IC50,
         curve statistics, Z'-factor): no role, with ``CALCULATED_BY_SOURCE``.
      4. **Readout synonym** ("signal", "% inhibition", …). Confidence: high.
      5. **Value-based fallback** — heuristics on cell values:
         - >80% match ``[A-Z]{1,2}\\d{1,2}`` → ``well``.
         - >80% dates → no role.
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

    # Build a normalized-name index for protocol-defined readouts.
    bindable_defs: dict[str, ReadoutDefRef] = {
        _norm(d.name): d
        for d in readout_defs
        if d.data_type in ("numeric", "text") and not d.derived
    }

    # Core-role synonyms claim their columns first, so a value guess on an
    # earlier column ("Run Date") can never take a role a later column names
    # outright ("Plate"). The first column per role wins.
    core: dict[int, Role] = {}
    for i, header in enumerate(table.headers):
        role = _synonym_role(header)
        if role is not None and role != "readout" and role not in core.values():
            core[i] = role
    role_taken: dict[Role, bool] = dict.fromkeys(core.values(), True)

    for i, header in enumerate(table.headers):
        # 1. Core-role synonym match
        if i in core:
            suggestions.append(
                HeaderSuggestion(
                    header=header,
                    role=core[i],
                    confidence="high",
                    reason="header matched synonym dictionary",
                )
            )
            continue

        # 2. Readout-definition name match, with or without a trailing unit
        bound_def = bindable_defs.get(_norm(header)) or bindable_defs.get(_norm(_stem(header)))
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

        # 3. Calculated by the source from the raw readout — Cellar calculates its own
        if _calculated_by_source(header, readout_defs):
            suggestions.append(
                HeaderSuggestion(
                    header=header, role=None, confidence="high", reason=CALCULATED_BY_SOURCE
                )
            )
            continue

        # 4. Readout synonym
        if _synonym_role(header) == "readout":
            suggestions.append(
                HeaderSuggestion(
                    header=header,
                    role="readout",
                    confidence="high",
                    reason="header matched synonym dictionary",
                )
            )
            role_taken["readout"] = True
            continue

        # 5. Value-based fallback
        values = [(r.get(header) or "").strip() for r in sample_rows]
        guess, conf, reason = _guess_role_from_values(values, role_taken)
        suggestions.append(
            HeaderSuggestion(header=header, role=guess, confidence=conf, reason=reason)
        )
        if guess is not None and guess != "readout":
            role_taken[guess] = True

    return SuggestedMapping(suggestions=tuple(suggestions))


def _stem(header: str) -> str:
    """The header without a trailing unit in parentheses: "raw AU (AU)" → "raw AU"."""
    return re.sub(r"\s*\([^()]*\)\s*$", "", header)


def _synonym_role(header: str) -> Role | None:
    for key in (_norm(header), _norm(_stem(header))):
        for role, syns in _SYNONYMS.items():
            if key in syns:
                return role
    return None


def _calculated_by_source(header: str, readout_defs: Sequence[ReadoutDefRef]) -> bool:
    """True when the column is one the source calculated from a raw readout
    the protocol imports — Cellar calculates its own, so it defaults to Ignore."""
    full, stem = _norm(header), _norm(_stem(header))
    if full.endswith(_PLATE_STATISTIC_SUFFIXES):
        return True
    fits_curves = False
    for d in readout_defs:
        name = _norm(d.name)
        if d.data_type == "dose_response":
            fits_curves = True
            # "IC50 (uM)", "IC50 CI (Lower) (uM)", "IC50 Fold Change"
            if name and stem.startswith(name):
                return True
        elif d.derived and name and stem == name:
            return True
        for n in d.normalizations:
            # "% inhibition (%)", "inhibition-50uM (%)"
            if any(stem.startswith(h) for h in _NORMALIZED_HEADERS.get(n, ())):
                return True
    return fits_curves and (
        stem in _CURVE_STATISTICS or stem.startswith(_CURVE_STATISTIC_PREFIXES)
    )


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

    # A date is never a plate name or a batch, however much it shares a prefix.
    if sum(1 for v in non_empty if _DATE_RE.match(v)) / len(non_empty) > 0.8:
        return None, "low", "values look like dates"

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
    - Concentration is parsed as float; missing/invalid/non-finite → ``None``.
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
        mapping.well_role,
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
    unknown_roles: dict[str, str] = {}  # _norm(value) -> first spelling
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

        well_role: WellType | None = None
        if mapping.well_role:
            role_cell = (raw.get(mapping.well_role) or "").strip()
            well_role = _WELL_ROLE_VALUES.get(_norm(role_cell))
            if well_role is None:
                unknown_roles.setdefault(_norm(role_cell), role_cell)

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
                well_role=well_role,
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
            unknown_well_roles=tuple(unknown_roles.values()),
            well_role_column=mapping.well_role,
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
        value = float(s)
    except ValueError:
        return None
    # "nan" and "inf" parse as floats but are not numbers a cell can hold:
    # treated like any other unparseable cell.
    return value if math.isfinite(value) else None


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
