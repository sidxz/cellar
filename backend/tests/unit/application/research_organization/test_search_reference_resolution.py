"""SearchReferenceResolver runs on every live count and result page, so a
pasted list must cost one lookup — not one per id."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

from returns.result import Failure, Success

from cellar.application.research_organization.search_reference_resolution import (
    SearchReferenceResolver,
)


class _Processor:
    def process(self, smiles: str):
        if smiles == "bad":
            return Failure(ValueError("unparseable"))
        return Success(SimpleNamespace(structure=SimpleNamespace(inchi_key=f"KEY-{smiles}")))


async def test_external_ids_resolve_in_one_batch_lookup() -> None:
    ws, mol = uuid.uuid4(), uuid.uuid4()
    repo = AsyncMock()
    repo.find_identifiers_in_workspace = AsyncMock(return_value={"V-1": mol})
    query = {
        "criteria": [
            {
                "type": "keyword_list",
                "ref_type": "external_id",
                "values": [f"V-{i}" for i in range(500)],
            }
        ]
    }

    out = await SearchReferenceResolver(repo, _Processor())(ws, query)

    repo.find_identifiers_in_workspace.assert_awaited_once()
    assert out["criteria"][0] == {"type": "keyword_list", "ref_type": "uuid", "values": [str(mol)]}
    assert query["criteria"][0]["ref_type"] == "external_id"  # caller's dict untouched


async def test_smiles_lists_become_inchi_keys_without_db() -> None:
    repo = AsyncMock()
    query = {
        "criteria": [{"type": "keyword_list", "ref_type": "smiles", "values": ["CCO", "bad"]}]
    }

    out = await SearchReferenceResolver(repo, _Processor())(uuid.uuid4(), query)

    assert out["criteria"][0] == {
        "type": "keyword_list",
        "ref_type": "inchi_key",
        "values": ["KEY-CCO"],
    }
    repo.assert_not_called()
