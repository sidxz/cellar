"""Resolve user-supplied references in a search query before it is composed.

The SQL composer (infrastructure) can only match columns it sees. Two
criterion shapes carry values it cannot match directly:

- ``keyword_list`` by ``external_id`` (lives in the identifier table) or by
  ``smiles`` (must go through the registration standardizer) — resolved to
  molecule UUIDs via ``MoleculeResolver``.
- an ``exact`` structure match given as SMILES — standardized to the InChIKey
  registration stored for the molecule.

Both are what a chemist pastes in practice ("here are my vendor ids", "is
this structure registered?"), so they are resolved here rather than rejected.
"""

from __future__ import annotations

import copy
import uuid
from typing import Any

from returns.result import Failure

from cellar.application.chemical_registration.protocols import StructureProcessorProtocol
from cellar.application.shared.molecule_resolver import (
    MoleculeReference,
    MoleculeResolver,
    RefType,
)
from cellar.domain.research_organization.criteria_walker import walk_criteria

_RESOLVED_REF_TYPES = frozenset({RefType.EXTERNAL_ID.value, RefType.SMILES.value})


class SearchReferenceResolver:
    def __init__(
        self, resolver: MoleculeResolver, structure_processor: StructureProcessorProtocol
    ) -> None:
        self._resolver = resolver
        self._structure_processor = structure_processor

    async def __call__(self, workspace_id: uuid.UUID, query: dict[str, Any]) -> dict[str, Any]:
        """Return a copy of ``query`` with resolvable references rewritten.

        Raises ``ValueError`` (→ 422) for an exact-match SMILES that does not
        parse. Unresolved keyword-list entries are dropped; a list where
        nothing resolves matches no molecules.
        """
        resolved = copy.deepcopy(query)
        leaves: list[dict[str, Any]] = []
        walk_criteria(resolved.get("criteria"), leaves.append)
        for c in leaves:
            if c.get("type") == "keyword_list" and c.get("ref_type") in _RESOLVED_REF_TYPES:
                ref_type = RefType(c["ref_type"])
                refs = [
                    MoleculeReference(value=v, ref_type=ref_type) for v in c.get("values") or []
                ]
                hits, _ = await self._resolver.resolve(workspace_id, refs)
                c["ref_type"] = RefType.UUID.value
                c["values"] = sorted({str(h.molecule_id) for h in hits})
            elif _is_exact_smiles(c):
                processed = self._structure_processor.process(c["smiles"].strip())
                if isinstance(processed, Failure):
                    msg = f"Cannot parse SMILES for exact match: {c['smiles']!r}"
                    raise ValueError(msg)
                c["inchi_key"] = processed.unwrap().structure.inchi_key
        return resolved


def _is_exact_smiles(c: dict[str, Any]) -> bool:
    kind = c.get("kind") or c.get("search_type")
    return (
        c.get("type") == "structure"
        and kind == "exact"
        and not c.get("inchi_key")
        and bool(c.get("smiles"))
    )
