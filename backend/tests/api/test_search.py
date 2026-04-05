"""API tests for search execution endpoint."""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient


@pytest.fixture
async def org_id(client: AsyncClient) -> str:
    """Create an organization so molecules can reference it."""
    resp = await client.post(
        "/api/v1/organizations",
        json={
            "name": "SearchTestOrg",
            "org_type": "internal",
        },
    )
    assert resp.status_code == 201
    return resp.json()["id"]


class TestExecuteSearch:
    async def test_empty_criteria_returns_all(
        self, client: AsyncClient, org_id: str
    ) -> None:
        """Empty criteria should return molecules (no filter)."""
        await client.post(
            "/api/v1/molecules",
            json={"name": "Mol A", "smiles": "C", "originating_org_id": org_id},
        )
        resp = await client.post(
            "/api/v1/search/execute",
            json={"query": {"criteria": [], "logic": "and"}},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["items"]) >= 1

    async def test_text_name_contains(
        self, client: AsyncClient, org_id: str
    ) -> None:
        await client.post(
            "/api/v1/molecules",
            json={"name": "SearchTarget", "smiles": "CC", "originating_org_id": org_id},
        )
        await client.post(
            "/api/v1/molecules",
            json={"name": "Other", "smiles": "CCC", "originating_org_id": org_id},
        )
        resp = await client.post(
            "/api/v1/search/execute",
            json={
                "query": {
                    "criteria": [
                        {"type": "text", "field": "name", "operator": "contains", "value": "SearchTarget"}
                    ],
                    "logic": "and",
                }
            },
        )
        assert resp.status_code == 200
        items = resp.json()["items"]
        assert any(m["name"] == "SearchTarget" for m in items)
        assert not any(m["name"] == "Other" for m in items)

    async def test_property_mw_between(
        self, client: AsyncClient, org_id: str
    ) -> None:
        """Register ethanol (MW ~46) and filter by MW range."""
        await client.post(
            "/api/v1/molecules",
            json={"name": "Ethanol", "smiles": "CCO", "originating_org_id": org_id},
        )
        resp = await client.post(
            "/api/v1/search/execute",
            json={
                "query": {
                    "criteria": [
                        {"type": "property", "field": "molecular_weight", "operator": "between", "min": 40, "max": 50}
                    ],
                    "logic": "and",
                }
            },
        )
        assert resp.status_code == 200
        items = resp.json()["items"]
        assert any(m["name"] == "Ethanol" for m in items)

    async def test_saved_search_execution(
        self, client: AsyncClient, org_id: str
    ) -> None:
        """Create saved search, register molecule, execute saved search."""
        await client.post(
            "/api/v1/molecules",
            json={"name": "SavedTarget", "smiles": "CCCC", "originating_org_id": org_id},
        )
        ss = await client.post(
            "/api/v1/saved-searches",
            json={
                "name": "Find SavedTarget",
                "query": {
                    "criteria": [
                        {"type": "text", "field": "name", "operator": "contains", "value": "SavedTarget"}
                    ],
                    "logic": "and",
                },
            },
        )
        assert ss.status_code == 201
        ss_id = ss.json()["id"]

        resp = await client.post(
            "/api/v1/search/execute",
            json={"saved_search_id": ss_id},
        )
        assert resp.status_code == 200
        items = resp.json()["items"]
        assert any(m["name"] == "SavedTarget" for m in items)

    async def test_no_query_or_saved_search_422(self, client: AsyncClient) -> None:
        resp = await client.post("/api/v1/search/execute", json={})
        assert resp.status_code == 422

    async def test_saved_search_not_found_404(self, client: AsyncClient) -> None:
        resp = await client.post(
            "/api/v1/search/execute",
            json={"saved_search_id": str(uuid.uuid4())},
        )
        assert resp.status_code == 404

    async def test_pagination(
        self, client: AsyncClient, org_id: str
    ) -> None:
        """Verify cursor pagination works on search results."""
        for i in range(3):
            await client.post(
                "/api/v1/molecules",
                json={"name": f"PageMol{i}", "smiles": f"{'C' * (i + 5)}", "originating_org_id": org_id},
            )
        resp = await client.post(
            "/api/v1/search/execute?limit=2",
            json={
                "query": {
                    "criteria": [
                        {"type": "text", "field": "name", "operator": "contains", "value": "PageMol"}
                    ],
                    "logic": "and",
                }
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["items"]) == 2
        assert data["next_cursor"] is not None

        # Fetch next page
        resp2 = await client.post(
            f"/api/v1/search/execute?limit=2&cursor={data['next_cursor']}",
            json={
                "query": {
                    "criteria": [
                        {"type": "text", "field": "name", "operator": "contains", "value": "PageMol"}
                    ],
                    "logic": "and",
                }
            },
        )
        assert resp2.status_code == 200
        data2 = resp2.json()
        assert len(data2["items"]) >= 1

    async def test_invalid_field_422(self, client: AsyncClient) -> None:
        resp = await client.post(
            "/api/v1/search/execute",
            json={
                "query": {
                    "criteria": [
                        {"type": "text", "field": "nonexistent", "operator": "contains", "value": "x"}
                    ],
                    "logic": "and",
                }
            },
        )
        assert resp.status_code == 422
