"""API tests for discriminated-union structure clause validation (T18)."""

from __future__ import annotations

import pytest
from httpx import AsyncClient


class TestStructureClauseValidation:
    """Pydantic discriminated-union validation fires at the API boundary."""

    async def test_unknown_kind_returns_422(self, client: AsyncClient) -> None:
        r = await client.post(
            "/api/v1/search/execute",
            json={"query": {"criteria": [
                {"type": "structure", "kind": "fancy", "smiles": "CCO"},
            ]}},
        )
        assert r.status_code == 422

    async def test_similarity_threshold_out_of_range_returns_422(
        self, client: AsyncClient
    ) -> None:
        r = await client.post(
            "/api/v1/search/execute",
            json={"query": {"criteria": [{
                "type": "structure", "kind": "similarity", "smiles": "CCO",
                "mode": "similar", "threshold": 1.5,
            }]}},
        )
        assert r.status_code == 422

    async def test_unknown_algorithm_returns_422(self, client: AsyncClient) -> None:
        r = await client.post(
            "/api/v1/search/execute",
            json={"query": {"criteria": [{
                "type": "structure", "kind": "similarity", "smiles": "CCO",
                "algorithm": "map4_v9", "metric": {"kind": "tanimoto"}, "threshold": 0.7,
            }]}},
        )
        assert r.status_code == 422

    async def test_invalid_smiles_returns_422(self, client: AsyncClient) -> None:
        r = await client.post(
            "/api/v1/search/execute",
            json={"query": {"criteria": [{
                "type": "structure", "kind": "similarity",
                "smiles": "XYZ-NOT-A-SMILES",
                "mode": "similar",
            }]}},
        )
        assert r.status_code == 422

    async def test_valid_similarity_returns_200(self, client: AsyncClient) -> None:
        r = await client.post(
            "/api/v1/search/execute",
            json={"query": {"criteria": [{
                "type": "structure", "kind": "similarity", "smiles": "CCO",
                "mode": "similar",
            }]}},
        )
        # 200 with empty results is fine; we just want the validator to not 422.
        assert r.status_code == 200, r.text

    async def test_validates_inside_groups(self, client: AsyncClient) -> None:
        """Nested groups must be walked too — bad structure inside a group → 422."""
        r = await client.post(
            "/api/v1/search/execute",
            json={"query": {"criteria": [
                {
                    "type": "group",
                    "logic": "and",
                    "criteria": [
                        {"type": "structure", "kind": "similarity",
                         "smiles": "CCO", "threshold": 5.0, "mode": "similar"},
                    ],
                }
            ]}},
        )
        assert r.status_code == 422

    async def test_exact_match_valid_inchi_key(self, client: AsyncClient) -> None:
        # Exact match with inchi_key passes validation and reaches the composer.
        r = await client.post(
            "/api/v1/search/execute",
            json={"query": {"criteria": [{
                "type": "structure", "kind": "exact",
                "inchi_key": "LFQSCWFLJHTTHZ-UHFFFAOYSA-N",
            }]}},
        )
        assert r.status_code == 200, r.text

    async def test_exact_match_requires_smiles_or_inchi_key(
        self, client: AsyncClient
    ) -> None:
        r = await client.post(
            "/api/v1/search/execute",
            json={"query": {"criteria": [{
                "type": "structure", "kind": "exact",
            }]}},
        )
        assert r.status_code == 422

    async def test_substructure_missing_pattern_returns_422(
        self, client: AsyncClient
    ) -> None:
        r = await client.post(
            "/api/v1/search/execute",
            json={"query": {"criteria": [{
                "type": "structure", "kind": "substructure",
            }]}},
        )
        assert r.status_code == 422

    async def test_legacy_search_type_key_accepted(self, client: AsyncClient) -> None:
        """search_type is accepted as a legacy alias for kind."""
        r = await client.post(
            "/api/v1/search/execute",
            json={"query": {"criteria": [{
                "type": "structure", "search_type": "similarity",
                "smiles": "CCO", "mode": "similar",
            }]}},
        )
        assert r.status_code == 200, r.text


class TestSubstructureQueryKindValidation:
    """query_kind disambiguates how the cartridge interprets the query string."""

    async def test_query_kind_smiles_accepts_smiles(self, client: AsyncClient) -> None:
        r = await client.post(
            "/api/v1/search/execute",
            json={"query": {"criteria": [{
                "type": "structure", "kind": "substructure",
                "query_kind": "smiles", "smiles_or_smarts": "c1ccccc1",
            }]}},
        )
        assert r.status_code == 200, r.text

    async def test_query_kind_smiles_rejects_smarts_only(
        self, client: AsyncClient
    ) -> None:
        """Atom-list SMARTS isn't valid SMILES — validator must reject."""
        r = await client.post(
            "/api/v1/search/execute",
            json={"query": {"criteria": [{
                "type": "structure", "kind": "substructure",
                "query_kind": "smiles", "smiles_or_smarts": "[N,O]CC",
            }]}},
        )
        assert r.status_code == 422

    async def test_query_kind_smarts_accepts_atom_list(
        self, client: AsyncClient
    ) -> None:
        r = await client.post(
            "/api/v1/search/execute",
            json={"query": {"criteria": [{
                "type": "structure", "kind": "substructure",
                "query_kind": "smarts", "smiles_or_smarts": "[N,O]CC",
            }]}},
        )
        assert r.status_code == 200, r.text

    async def test_generalized_with_smarts_kind_returns_422(
        self, client: AsyncClient
    ) -> None:
        """Generalized matching needs a real `mol`; SMARTS+generalized is
        rejected at the API edge so the chemist gets a clear signal."""
        r = await client.post(
            "/api/v1/search/execute",
            json={"query": {"criteria": [{
                "type": "structure", "kind": "substructure",
                "query_kind": "smarts", "smiles_or_smarts": "[N,O]CC",
                "generalized": True,
            }]}},
        )
        assert r.status_code == 422

    async def test_generalized_with_smiles_kind_accepted(
        self, client: AsyncClient
    ) -> None:
        r = await client.post(
            "/api/v1/search/execute",
            json={"query": {"criteria": [{
                "type": "structure", "kind": "substructure",
                "query_kind": "smiles", "smiles_or_smarts": "c1ccccc1",
                "generalized": True,
            }]}},
        )
        assert r.status_code == 200, r.text

    async def test_legacy_no_query_kind_still_works(
        self, client: AsyncClient
    ) -> None:
        """Untagged criteria (saved searches predating query_kind) keep
        validating against the either-parses rule."""
        r = await client.post(
            "/api/v1/search/execute",
            json={"query": {"criteria": [{
                "type": "structure", "kind": "substructure",
                "smiles_or_smarts": "[#6]1-[#6]=[#6]-[#6]=[#6]-[#6]=1",
            }]}},
        )
        assert r.status_code == 200, r.text
