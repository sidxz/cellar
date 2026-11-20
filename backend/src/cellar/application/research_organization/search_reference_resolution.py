"""Resolve user-supplied references in a search query before it is composed.

The SQL composer (infrastructure) can only match what is stored. A pasted
SMILES is not: registration stored the standardized structure's InChIKey. So
two criterion shapes are standardized here the way registration did it:

- a ``keyword_list`` by ``smiles`` — matched as InChIKeys;
- an ``exact`` structure match given as SMILES.

External IDs need no resolution: the composer matches them in the identifier
table itself, case-insensitively like every other keyword field.
"""

from __future__ import annotations

import copy
import uuid
from typing import Any

from returns.result import Failure

from cellar.application.chemical_registration.protocols import StructureProcessorProtocol
from cellar.domain.research_organization.criteria_walker import walk_criteria


class SearchReferenceResolver:
    def __init__(self, structure_processor: StructureProcessorProtocol) -> None:
        self._structure_processor = structure_processor

    async def __call__(self, workspace_id: uuid.UUID, query: dict[str, Any]) -> dict[str, Any]:
        """Return a copy of ``query`` with resolvable references rewritten.

        Raises ``ValueError`` (→ 422) for an exact-match SMILES that does not
        parse. Unresolvable keyword-list entries are dropped; a list where
        nothing resolves matches no molecules.
        """
        resolved = copy.deepcopy(query)
        leaves: list[dict[str, Any]] = []
        walk_criteria(resolved.get("criteria"), leaves.append)
        for c in leaves:
            if c.get("type") == "keyword_list" and c.get("ref_type") == "smiles":
                keys = (self._inchi_key(v) for v in c.get("values") or [])
                c["ref_type"] = "inchi_key"
                c["values"] = sorted({k for k in keys if k})
                if not c["values"]:  # nothing parsed → match nothing, not 422
                    c["ref_type"], c["values"] = "uuid", []
            elif _is_exact_smiles(c):
                key = self._inchi_key(c["smiles"])
                if key is None:
                    msg = f"Cannot parse SMILES for exact match: {c['smiles']!r}"
                    raise ValueError(msg)
                c["inchi_key"] = key
        return resolved

    def _inchi_key(self, smiles: str) -> str | None:
        """InChIKey of the structure as registration standardizes it."""
        processed = self._structure_processor.process(smiles.strip())
        if isinstance(processed, Failure):
            return None
        return processed.unwrap().structure.inchi_key


def _is_exact_smiles(c: dict[str, Any]) -> bool:
    kind = c.get("kind") or c.get("search_type")
    return (
        c.get("type") == "structure"
        and kind == "exact"
        and not c.get("inchi_key")
        and bool(c.get("smiles"))
    )
