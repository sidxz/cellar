"""SearchReferenceResolver standardizes pasted SMILES the way registration did,
and leaves every other keyword field for the SQL composer to match."""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
from returns.result import Failure, Success

from cellar.application.research_organization.search_reference_resolution import (
    SearchReferenceResolver,
)


class _Processor:
    def process(self, smiles: str):
        if smiles == "bad":
            return Failure(ValueError("unparseable"))
        return Success(SimpleNamespace(structure=SimpleNamespace(inchi_key=f"KEY-{smiles}")))


async def test_smiles_lists_become_inchi_keys() -> None:
    query = {
        "criteria": [{"type": "keyword_list", "ref_type": "smiles", "values": ["CCO", "bad"]}]
    }

    out = await SearchReferenceResolver(_Processor())(uuid.uuid4(), query)

    assert out["criteria"][0] == {
        "type": "keyword_list",
        "ref_type": "inchi_key",
        "values": ["KEY-CCO"],
    }
    assert query["criteria"][0]["ref_type"] == "smiles"  # caller's dict untouched


@pytest.mark.parametrize("operator", ["equals", "starts_with", None])
async def test_external_id_lists_are_left_for_the_sql_composer(operator: str | None) -> None:
    criterion = {
        "type": "keyword_list",
        "ref_type": "external_id",
        "values": ["VENDOR-", "kino-77"],
    }
    if operator:
        criterion["operator"] = operator
    query = {"criteria": [criterion]}

    assert await SearchReferenceResolver(_Processor())(uuid.uuid4(), query) == query
