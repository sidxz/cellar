"""Synonym-based header → role suggestion for the collection-import wizard.

Mirrors the shape of `application/screening/long_format_normalizer.py`'s
synonym dictionary but covers the collection roles (no plate / well /
concentration / readout).
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True, kw_only=True)
class HeaderSuggestion:
    header: str
    role: str | None
    reason: str


# role → list of normalized synonyms
_SYNONYMS: dict[str, list[str]] = {
    "registration_number": [
        "regno", "reg", "regnumber", "registrationnumber", "registration",
        "compoundid", "cellarid", "ccnumber", "ccno", "compoundnumber",
    ],
    "external_id": [
        "externalid", "vendorid", "vendorlot", "cas", "casnumber",
        "chemblid", "pubchemid", "suppliercode", "catalogno", "sku",
        "lotid", "lotnumber",
    ],
    "inchi_key": ["inchikey", "inchi"],
    "smiles": ["smiles", "canonicalsmiles", "structure", "molsmiles"],
    "name": [
        "name", "compoundname", "moleculename", "commonname", "title",
        "label", "compound",
    ],
    "notes": ["notes", "note", "comment", "comments", "description", "remark"],
}


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", s.lower())


def suggest_column_mapping(headers: list[str]) -> list[HeaderSuggestion]:
    """Return one HeaderSuggestion per CSV header, in input order.

    `role` is None when no synonym matches; the FE renders these with an
    empty select that the chemist can set manually.
    """
    suggestions: list[HeaderSuggestion] = []
    for header in headers:
        normalized = _norm(header)
        matched_role: str | None = None
        for role, syns in _SYNONYMS.items():
            if normalized in syns:
                matched_role = role
                break
        suggestions.append(
            HeaderSuggestion(
                header=header,
                role=matched_role,
                reason="synonym match" if matched_role else "no match",
            )
        )
    return suggestions
