"""End-to-end HTTP smoke for /api/v1/search/execute.

Sister file to ``tests/integration/search/test_composer_executes.py``: those
verify the composer SQL executes against the cartridge; these verify the
*full* request path — Pydantic validation, route handler, use case,
composer, asyncpg driver, cartridge — produces HTTP 200 (not 500).

The bug class this guards against is the same one that bit twice during
development: SQLAlchemy bindparam types pushing VARCHAR/BYTEA where the
cartridge needs cstring/bfp, manifesting as
``UndefinedFunctionError: function qmol_from_smarts(character varying)
does not exist`` and surfacing only when a real driver round-trips the
parameter. Unit tests can't see this; only execute-tier tests can.

Hit counts here are best-effort — the API client uses its own DB session
separate from any other test data, so we only assert HTTP semantics, not
result contents (the integration-test sister file asserts hits).
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.fixture
async def org_id(client: AsyncClient) -> str:
    """One organization is needed before molecules can be registered."""
    resp = await client.post(
        "/api/v1/organizations",
        json={"name": "SearchExecOrg", "org_type": "internal"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


@pytest.fixture
async def benzene_registered(client: AsyncClient, org_id: str) -> str:
    """Register a benzene so the structure clauses have something to find."""
    resp = await client.post(
        "/api/v1/molecules",
        json={
            "name": "benzene-smoke",
            "smiles": "c1ccccc1",
            "molecule_type": "small_molecule",
            "originating_org_id": org_id,
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["molecule"]["id"]


def _structure_query(criterion: dict) -> dict:
    return {"query": {"criteria": [{"type": "structure", **criterion}], "logic": "and"}}


class TestSubstructureRouteExecutes:
    async def test_strict_substructure_returns_200(
        self,
        client: AsyncClient,
        benzene_registered: str,
    ) -> None:
        resp = await client.post(
            "/api/v1/search/execute",
            json=_structure_query({
                "kind": "substructure",
                "smiles_or_smarts": "c1ccccc1",
            }),
        )
        assert resp.status_code == 200, resp.text
        item_ids = {it["id"] for it in resp.json()["items"]}
        assert benzene_registered in item_ids

    async def test_legacy_substructure_returns_200(
        self,
        client: AsyncClient,
        benzene_registered: str,
    ) -> None:
        """Legacy {search_type: substructure, smarts: ...} continues to work."""
        resp = await client.post(
            "/api/v1/search/execute",
            json=_structure_query({
                "search_type": "substructure",
                "smarts": "c1ccccc1",
            }),
        )
        assert resp.status_code == 200, resp.text

    async def test_generalized_substructure_returns_200(
        self,
        client: AsyncClient,
        benzene_registered: str,
    ) -> None:
        resp = await client.post(
            "/api/v1/search/execute",
            json=_structure_query({
                "kind": "substructure",
                "smiles_or_smarts": "c1ccccc1",
                "generalized": True,
            }),
        )
        assert resp.status_code == 200, resp.text


class TestSimilarityRouteExecutes:
    async def test_similar_mode_returns_200(
        self,
        client: AsyncClient,
        benzene_registered: str,
    ) -> None:
        resp = await client.post(
            "/api/v1/search/execute",
            json=_structure_query({
                "kind": "similarity",
                "smiles": "c1ccccc1",
                "mode": "similar",
            }),
        )
        assert resp.status_code == 200, resp.text
        item_ids = {it["id"] for it in resp.json()["items"]}
        assert benzene_registered in item_ids

    async def test_scaffold_hop_mode_returns_200(
        self,
        client: AsyncClient,
        benzene_registered: str,
    ) -> None:
        resp = await client.post(
            "/api/v1/search/execute",
            json=_structure_query({
                "kind": "similarity",
                "smiles": "c1ccccc1",
                "mode": "scaffold_hop",
            }),
        )
        assert resp.status_code == 200, resp.text

    async def test_fragment_in_target_mode_returns_200(
        self,
        client: AsyncClient,
        benzene_registered: str,
    ) -> None:
        resp = await client.post(
            "/api/v1/search/execute",
            json=_structure_query({
                "kind": "similarity",
                "smiles": "c1ccccc1",
                "mode": "fragment_in_target",
            }),
        )
        assert resp.status_code == 200, resp.text

    async def test_legacy_similarity_returns_200(
        self,
        client: AsyncClient,
        benzene_registered: str,
    ) -> None:
        """Legacy {search_type: similarity, smiles, threshold} continues to work."""
        resp = await client.post(
            "/api/v1/search/execute",
            json=_structure_query({
                "search_type": "similarity",
                "smiles": "c1ccccc1",
                "threshold": 0.5,
            }),
        )
        assert resp.status_code == 200, resp.text


class TestQuickSearchEndpointExecutes:
    """The legacy GET /api/v1/molecules/search bar uses a different code path
    (SearchMolecules use case + SQLAlchemyMoleculeRepository.search_substructure
    or .search_similarity). Same bind-type concerns apply, so smoke it too."""

    async def test_legacy_substructure_endpoint(
        self,
        client: AsyncClient,
        benzene_registered: str,
    ) -> None:
        resp = await client.get(
            "/api/v1/molecules/search",
            params={"search_type": "substructure", "query": "c1ccccc1"},
        )
        assert resp.status_code == 200, resp.text

    async def test_legacy_similarity_endpoint(
        self,
        client: AsyncClient,
        benzene_registered: str,
    ) -> None:
        resp = await client.get(
            "/api/v1/molecules/search",
            params={"search_type": "similarity", "query": "c1ccccc1", "threshold": 0.5},
        )
        assert resp.status_code == 200, resp.text

    async def test_legacy_exact_endpoint(
        self,
        client: AsyncClient,
        benzene_registered: str,
    ) -> None:
        resp = await client.get(
            "/api/v1/molecules/search",
            params={"search_type": "exact", "query": "c1ccccc1"},
        )
        assert resp.status_code == 200, resp.text
