"""ColumnMapping — which column of a bulk-registration file goes where.

Application-layer value object. The wizard's "Match columns" step builds one;
it travels with the upload (form field → workflow input → parse activity) and
the infrastructure parser applies it. Without one, the parser applies
``suggest_column_mapping`` to the file's headers (spec 2026-11-18 §3): a file using
the fixed parser's header names reads as it always did, and synonym and batch-ID
headers, which that parser ignored, are read too.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from enum import StrEnum
from typing import Any

from cellar.domain.chemical_registration.enums import MoleculeType
from cellar.domain.inventory.enums import BatchSource
from cellar.domain.shared.enums import AmountUnit
from cellar.domain.shared.errors import ValidationError

SDF_TITLE_HEADER = "Title line"

# Identifier and Source columns are String(255) (molecule_identifiers, batch_identifiers).
MAX_ID_LENGTH = 255


class ColumnTarget(StrEnum):
    NAME = "name"
    SMILES = "smiles"
    MOLECULE_TYPE = "molecule_type"
    COMPOUND_ID = "compound_id"
    CAS_NUMBER = "cas_number"
    CHEMBL_ID = "chembl_id"
    PUBCHEM_CID = "pubchem_cid"
    VENDOR_ID = "vendor_id"
    BATCH_ID = "batch_id"
    AMOUNT_VALUE = "amount_value"
    AMOUNT_UNIT = "amount_unit"
    SALT_CODE = "salt_code"
    SALT_STOICHIOMETRY = "salt_stoichiometry"
    PURITY = "purity"
    BATCH_SOURCE = "batch_source"
    APPEARANCE = "appearance"
    IGNORE = "ignore"


# Targets whose values are stored as identifiers carrying a Source label.
LABELLED_TARGETS = frozenset(
    {
        ColumnTarget.COMPOUND_ID,
        ColumnTarget.CAS_NUMBER,
        ColumnTarget.CHEMBL_ID,
        ColumnTarget.PUBCHEM_CID,
        ColumnTarget.VENDOR_ID,
        ColumnTarget.BATCH_ID,
    }
)
# Targets more than one column may go to.
MULTI_TARGETS = frozenset({ColumnTarget.COMPOUND_ID, ColumnTarget.BATCH_ID, ColumnTarget.IGNORE})
# Compound-level identifier targets → MoleculeIdentifier.identifier_type.
COMPOUND_ID_TYPES: dict[ColumnTarget, str] = {
    ColumnTarget.COMPOUND_ID: "custom",
    ColumnTarget.CAS_NUMBER: "cas_number",
    ColumnTarget.CHEMBL_ID: "chembl_id",
    ColumnTarget.PUBCHEM_CID: "pubchem_cid",
    ColumnTarget.VENDOR_ID: "vendor_id",
}


@dataclass(frozen=True)
class MappedColumn:
    header: str
    target: ColumnTarget
    source: str | None = None
    # How a multi-value ID cell is split besides line breaks: only ";" (or None).
    separator: str | None = None


@dataclass(frozen=True)
class ColumnMapping:
    columns: tuple[MappedColumn, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "columns": [
                {
                    "header": c.header,
                    "target": c.target.value,
                    "source": c.source,
                    "separator": c.separator,
                }
                for c in self.columns
            ]
        }

    @classmethod
    def from_dict(cls, d: object) -> ColumnMapping:
        raw = d.get("columns") if isinstance(d, dict) else None
        if not isinstance(raw, list):
            raise ValidationError("column_mapping needs a 'columns' list")
        cols: list[MappedColumn] = []
        for c in raw:
            if not isinstance(c, dict) or not isinstance(c.get("header"), str):
                raise ValidationError("Each mapped column needs a 'header'")
            try:
                target = ColumnTarget(str(c.get("target")))
            except ValueError:
                raise ValidationError(
                    f"Column '{c['header']}': unknown target {c.get('target')!r}"
                ) from None
            source = c.get("source")
            separator = c.get("separator")
            cols.append(
                MappedColumn(
                    header=c["header"],
                    target=target,
                    source=source.strip() if isinstance(source, str) and source.strip() else None,
                    separator=separator if isinstance(separator, str) and separator else None,
                )
            )
        return cls(columns=tuple(cols))

    def validate(
        self, headers: Sequence[str], *, structure_implied: bool
    ) -> ValidationError | None:
        known = set(headers)
        taken: dict[ColumnTarget, str] = {}
        for c in self.columns:
            if c.target == ColumnTarget.IGNORE:
                continue  # nothing is read from it, so it need not be there
            if c.header not in known:
                return ValidationError(f"Column '{c.header}' is not in the file")
            if c.target not in MULTI_TARGETS:
                if c.target in taken:
                    return ValidationError(
                        f"Columns '{taken[c.target]}' and '{c.header}' both go to "
                        f"{c.target.value}; only one column can"
                    )
                taken[c.target] = c.header
            if c.separator is not None and (
                c.separator != ";"
                or c.target not in (ColumnTarget.COMPOUND_ID, ColumnTarget.BATCH_ID)
            ):
                return ValidationError(
                    f"Column '{c.header}': only an ID column can be split, and only on ';'"
                )
            if c.target in LABELLED_TARGETS and not c.source:
                return ValidationError(f"Column '{c.header}' needs a Source")
            if c.source and len(c.source) > MAX_ID_LENGTH:
                return ValidationError(
                    f"The Source for column '{c.header}' is longer than {MAX_ID_LENGTH} characters"
                )
        if not structure_implied and not (
            ColumnTarget.NAME in taken or ColumnTarget.SMILES in taken
        ):
            return ValidationError("Pick the column with the compound name or the structure")
        return None

    def without_sources(self) -> ColumnMapping:
        return ColumnMapping(columns=tuple(replace(c, source=None) for c in self.columns))


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", s.lower())


# Normalised header → target. Today's fixed parser aliases plus general synonyms.
_SUGGESTIONS: dict[str, ColumnTarget] = {
    **dict.fromkeys(
        ["name", "compoundname", "molname", "moleculename", "title"], ColumnTarget.NAME
    ),
    **dict.fromkeys(["smiles", "canonicalsmiles", "structure", "molsmiles"], ColumnTarget.SMILES),
    **dict.fromkeys(["moleculetype", "moltype", "type"], ColumnTarget.MOLECULE_TYPE),
    **dict.fromkeys(["cas", "casnumber", "casno"], ColumnTarget.CAS_NUMBER),
    **dict.fromkeys(
        ["vendorid", "vendorcode", "catalognumber", "catalogno"], ColumnTarget.VENDOR_ID
    ),
    **dict.fromkeys(["chemblid", "chembl"], ColumnTarget.CHEMBL_ID),
    **dict.fromkeys(["pubchemcid", "pubchem", "pubchemid"], ColumnTarget.PUBCHEM_CID),
    **dict.fromkeys(
        [
            "synonym",
            "synonyms",
            "alias",
            "aliases",
            "alternatename",
            "alternatenames",
            "othername",
            "othernames",
        ],
        ColumnTarget.COMPOUND_ID,
    ),
    **dict.fromkeys(
        ["batchid", "lotid", "lotnumber", "externalbatchid", "legacybatchid"],
        ColumnTarget.BATCH_ID,
    ),
    **dict.fromkeys(["amount", "amountvalue", "quantity"], ColumnTarget.AMOUNT_VALUE),
    **dict.fromkeys(["amountunit", "unit"], ColumnTarget.AMOUNT_UNIT),
    **dict.fromkeys(["salt", "saltcode", "saltform"], ColumnTarget.SALT_CODE),
    **dict.fromkeys(["saltstoichiometry", "stoichiometry"], ColumnTarget.SALT_STOICHIOMETRY),
    **dict.fromkeys(["purity", "puritypercent"], ColumnTarget.PURITY),
    **dict.fromkeys(["source", "batchsource"], ColumnTarget.BATCH_SOURCE),
    "appearance": ColumnTarget.APPEARANCE,
}


def _suggest_one(header: str) -> ColumnTarget:
    if header == SDF_TITLE_HEADER:
        return ColumnTarget.NAME
    n = _norm(header)
    if n.startswith("customid"):  # custom_id, custom_id_1, …
        return ColumnTarget.COMPOUND_ID
    return _SUGGESTIONS.get(n, ColumnTarget.IGNORE)


def suggest_column_mapping(headers: Sequence[str]) -> ColumnMapping:
    """One column per header, in file order. A single-valued target suggested by a
    second header falls back to ``ignore``; labelled targets get the header as Source."""
    taken: set[ColumnTarget] = set()
    cols: list[MappedColumn] = []
    for h in headers:
        target = _suggest_one(h)
        if target not in MULTI_TARGETS:
            if target in taken:
                target = ColumnTarget.IGNORE
            else:
                taken.add(target)
        cols.append(
            MappedColumn(header=h, target=target, source=h if target in LABELLED_TARGETS else None)
        )
    return ColumnMapping(columns=tuple(cols))


def split_multi(value: str, separator: str | None = None) -> list[str]:
    """Split a multi-value cell on line breaks (and ``separator``, if given) — names
    contain commas and spaces, so nothing else splits."""
    pattern = r"\r\n|\n|\r" + (f"|{re.escape(separator)}" if separator else "")
    return [p.strip() for p in re.split(pattern, value) if p.strip()]


def is_cas_number(value: str) -> bool:
    """CAS Registry Number: ``NNNNN-NN-C`` with a valid check digit."""
    if not re.fullmatch(r"\d{2,7}-\d{2}-\d", value):
        return False
    digits = value.replace("-", "")
    body, check = digits[:-1], int(digits[-1])
    return sum(i * int(d) for i, d in enumerate(reversed(body), 1)) % 10 == check


@dataclass(frozen=True)
class ExtractedRow:
    name: str | None
    smiles: str | None
    molecule_type: str
    external_ids: list[dict[str, str]]  # {"identifier", "identifier_type", optional "source"}
    batch_ids: list[dict[str, str]]  # {"identifier", "source"}
    warnings: list[str]
    amount_value: float | None
    amount_unit: str
    salt_code: str | None
    salt_stoichiometry: int
    purity: float | None
    batch_source: str
    appearance: str | None


_DEFAULT_BATCH_ID_SOURCE = "Bulk registration"


def _float(s: str | None) -> float | None:
    try:
        return float(s) if s else None
    except ValueError:
        return None


def _int(s: str | None) -> int | None:
    f = _float(s)
    return int(f) if f is not None else None


# Targets that take one of a fixed list; what is stored when the row has none.
_CHOICES: dict[ColumnTarget, tuple[type[StrEnum], str]] = {
    ColumnTarget.MOLECULE_TYPE: (MoleculeType, "registered as small_molecule"),
    ColumnTarget.AMOUNT_UNIT: (AmountUnit, "the amount is not stored"),
    ColumnTarget.BATCH_SOURCE: (BatchSource, "recorded as synthesized"),
}


def _choice(choices: type[StrEnum], value: str) -> str | None:
    """The listed value ``value`` means, ignoring case, spaces, ``_`` and ``-`` only
    (``_norm`` would read "µg" as "g")."""

    def n(s: str) -> str:
        return re.sub(r"[\s_-]+", "", s.lower())

    return next((m.value for m in choices if n(m.value) == n(value)), None)


def extract_row(
    get: Callable[[str], str | list[str] | None],
    mapping: ColumnMapping,
    *,
    structure: str | None = None,
) -> ExtractedRow | None:
    """Apply a mapping to one row. ``get(header)`` returns the cell (trimmed), a list
    of values, or None. ``structure`` (SDF) wins over a mapped structure column.
    Returns None when the row has neither a name nor a structure."""
    single: dict[ColumnTarget, str] = {}
    external_ids: list[dict[str, str]] = []
    batch_ids: list[dict[str, str]] = []
    warnings: list[str] = []
    amount_unknown = False  # an amount in a unit ChemCellar doesn't know is not stored

    def fits(v: str, header: str) -> bool:
        if len(v) <= MAX_ID_LENGTH:
            return True
        warnings.append(
            f"{header}: '{v[:40]}…' is longer than {MAX_ID_LENGTH} characters "
            "and is not stored as an ID"
        )
        return False

    for col in mapping.columns:
        if col.target == ColumnTarget.IGNORE:
            continue
        val = get(col.header)
        if not val:
            continue
        if isinstance(val, list):
            values = [p.strip() for p in val if p and p.strip()]
        elif col.target in (ColumnTarget.COMPOUND_ID, ColumnTarget.BATCH_ID):
            values = split_multi(val, col.separator)
        else:
            values = [val]
        if col.target == ColumnTarget.BATCH_ID:
            for v in values:
                if fits(v, col.header):
                    batch_ids.append(
                        {"identifier": v, "source": col.source or _DEFAULT_BATCH_ID_SOURCE}
                    )
        elif col.target in COMPOUND_ID_TYPES:
            for v in values:
                if not fits(v, col.header):
                    continue
                id_type = COMPOUND_ID_TYPES[col.target]
                if col.target == ColumnTarget.COMPOUND_ID and is_cas_number(v):
                    id_type = "cas_number"
                eid = {"identifier": v, "identifier_type": id_type}
                if col.source:
                    eid["source"] = col.source
                external_ids.append(eid)
        elif values:
            single[col.target] = values[0]
            if col.target in _CHOICES:
                choices, fallback = _CHOICES[col.target]
                known = _choice(choices, values[0])
                if known is None:
                    del single[col.target]
                    listed = ", ".join(m.value for m in choices)
                    warnings.append(
                        f"{col.header}: '{values[0]}' is not one of {listed}; {fallback}"
                    )
                    if col.target == ColumnTarget.AMOUNT_UNIT:
                        amount_unknown = True
                else:
                    single[col.target] = known

    name = single.get(ColumnTarget.NAME)
    smiles = structure or single.get(ColumnTarget.SMILES)
    if not name and not smiles:
        return None
    stoich = _int(single.get(ColumnTarget.SALT_STOICHIOMETRY))
    return ExtractedRow(
        name=name,
        smiles=smiles,
        molecule_type=single.get(ColumnTarget.MOLECULE_TYPE) or "small_molecule",
        external_ids=external_ids,
        batch_ids=batch_ids,
        warnings=warnings,
        amount_value=None if amount_unknown else _float(single.get(ColumnTarget.AMOUNT_VALUE)),
        amount_unit=single.get(ColumnTarget.AMOUNT_UNIT) or "mg",
        salt_code=single.get(ColumnTarget.SALT_CODE),
        salt_stoichiometry=stoich if stoich is not None else 1,
        purity=_float(single.get(ColumnTarget.PURITY)),
        batch_source=single.get(ColumnTarget.BATCH_SOURCE) or "synthesized",
        appearance=single.get(ColumnTarget.APPEARANCE),
    )
