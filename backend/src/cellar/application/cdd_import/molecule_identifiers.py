"""Molecule identifiers a person listed: parse the list, match it to what the vault returned."""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

# ponytail: a list is checked inside one web request, one vault query after another
# (500 names each), hence the cap. Check in a background job if longer lists are needed.
MAX_IDENTIFIERS = 5000

# What separates identifiers in pasted text: new lines, commas, semicolons, tabs.
# Not spaces: vault names such as "16:0 CoA" contain them.
_SEPARATORS = re.compile(r"[\n\r,;\t]+")


@dataclass(frozen=True)
class IdentifierMatch:
    found: list[str]  # identifiers that name a vault molecule, in the order given
    not_found: list[str]
    molecule_ids: list[int]  # the vault's ids of the molecules named, each once


def _tidy(text: str) -> str:
    """Trimmed, with each run of inner white space as one space."""
    return " ".join(text.split())


def parse_identifiers(text: str) -> list[str]:
    """The identifiers in pasted text: one per line, or separated by commas, semicolons or tabs."""
    return clean_identifiers(_SEPARATORS.split(text))


def clean_identifiers(raw: Iterable[str]) -> list[str]:
    """Each entry tidied; blanks and duplicates dropped (ignoring case; first spelling stays)."""
    by_key: dict[str, str] = {}
    for item in raw:
        text = _tidy(item)
        if text:
            by_key.setdefault(text.casefold(), text)
    return list(by_key.values())


def match_identifiers(identifiers: list[str], molecules: list[dict[str, Any]]) -> IdentifierMatch:
    """Which identifiers are the name or a synonym of one of ``molecules``, ignoring case.

    The vault did the search; this attributes its answer. A molecule it returned on a
    looser match than its whole name or synonym is left out.
    """
    wanted = {_tidy(identifier).casefold() for identifier in identifiers}
    named: set[str] = set()
    molecule_ids: dict[int, None] = {}
    for molecule in molecules:
        names = [molecule.get("name"), *(molecule.get("synonyms") or [])]
        hits = {_tidy(str(name)).casefold() for name in names if name} & wanted
        if hits:
            named |= hits
            molecule_ids[molecule["id"]] = None
    return IdentifierMatch(
        found=[i for i in identifiers if _tidy(i).casefold() in named],
        not_found=[i for i in identifiers if _tidy(i).casefold() not in named],
        molecule_ids=list(molecule_ids),
    )
