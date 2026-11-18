"""ColumnMapping — which column of a bulk-registration file goes where.

Application-layer value object. The wizard's "Match columns" step builds one;
it travels with the upload (form field → workflow input → parse activity) and
the infrastructure parser applies it. Without one, the parser applies
``suggest_column_mapping`` to the file's headers, which reproduces the fixed
header names the parser always accepted.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, replace
from enum import StrEnum
from typing import Any

from cellar.domain.shared.errors import ValidationError

SDF_TITLE_HEADER = "Title line"


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


@dataclass(frozen=True)
class ColumnMapping:
    columns: tuple[MappedColumn, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "columns": [
                {"header": c.header, "target": c.target.value, "source": c.source}
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
            cols.append(
                MappedColumn(
                    header=c["header"],
                    target=target,
                    source=source.strip() if isinstance(source, str) and source.strip() else None,
                )
            )
        return cls(columns=tuple(cols))

    def validate(
        self, headers: Sequence[str], *, structure_implied: bool
    ) -> ValidationError | None:
        known = set(headers)
        taken: dict[ColumnTarget, str] = {}
        for c in self.columns:
            if c.header not in known:
                return ValidationError(f"Column '{c.header}' is not in the file")
            if c.target not in MULTI_TARGETS:
                if c.target in taken:
                    return ValidationError(
                        f"Columns '{taken[c.target]}' and '{c.header}' both go to "
                        f"{c.target.value}; only one column can"
                    )
                taken[c.target] = c.header
            if c.target in LABELLED_TARGETS and not c.source:
                return ValidationError(f"Column '{c.header}' needs a Source")
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


def split_multi(value: str) -> list[str]:
    """Split a multi-value cell on line breaks only — names contain commas and spaces."""
    return [p.strip() for p in re.split(r"\r\n|\n|\r", value) if p.strip()]
