"""API tests for tagging endpoints (assignment uses collections — easy to create)."""

from __future__ import annotations

import uuid

from httpx import AsyncClient


async def _make_collection(client: AsyncClient, name: str) -> str:
    resp = await client.post("/api/v1/collections", json={"name": name})
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


class TestAssignAndRead:
    async def test_assign_then_get(self, client: AsyncClient) -> None:
        cid = await _make_collection(client, "TagCol-1")
        resp = await client.post(
            f"/api/v1/collections/{cid}/tags", json={"key": "Project", "value": "Alpha"}
        )
        assert resp.status_code == 201, resp.text
        tag = resp.json()
        assert tag["key"] == "Project"
        assert tag["value"] == "Alpha"

        got = await client.get(f"/api/v1/collections/{cid}/tags")
        assert got.status_code == 200
        assert [t["key"] for t in got.json()] == ["Project"]

    async def test_assign_valueless(self, client: AsyncClient) -> None:
        cid = await _make_collection(client, "TagCol-2")
        resp = await client.post(f"/api/v1/collections/{cid}/tags", json={"key": "favorite"})
        assert resp.status_code == 201
        assert resp.json()["value"] is None

    async def test_set_reconciles(self, client: AsyncClient) -> None:
        cid = await _make_collection(client, "TagCol-3")
        await client.post(f"/api/v1/collections/{cid}/tags", json={"key": "a"})
        await client.post(f"/api/v1/collections/{cid}/tags", json={"key": "b"})
        resp = await client.put(
            f"/api/v1/collections/{cid}/tags",
            json={"tags": [{"key": "b"}, {"key": "c"}]},
        )
        assert resp.status_code == 200
        assert {t["key"] for t in resp.json()} == {"b", "c"}
        got = await client.get(f"/api/v1/collections/{cid}/tags")
        assert {t["key"] for t in got.json()} == {"b", "c"}

    async def test_unassign(self, client: AsyncClient) -> None:
        cid = await _make_collection(client, "TagCol-4")
        created = await client.post(f"/api/v1/collections/{cid}/tags", json={"key": "x"})
        tag_id = created.json()["id"]
        resp = await client.delete(f"/api/v1/collections/{cid}/tags/{tag_id}")
        assert resp.status_code == 204
        got = await client.get(f"/api/v1/collections/{cid}/tags")
        assert got.json() == []


class TestErrors:
    async def test_assign_to_missing_collection_404(self, client: AsyncClient) -> None:
        resp = await client.post(
            f"/api/v1/collections/{uuid.uuid4()}/tags", json={"key": "x"}
        )
        assert resp.status_code == 404

    async def test_unknown_entity_collection_404(self, client: AsyncClient) -> None:
        resp = await client.post(
            f"/api/v1/widgets/{uuid.uuid4()}/tags", json={"key": "x"}
        )
        assert resp.status_code == 404

    async def test_empty_key_422(self, client: AsyncClient) -> None:
        cid = await _make_collection(client, "TagCol-5")
        resp = await client.post(f"/api/v1/collections/{cid}/tags", json={"key": "   "})
        assert resp.status_code == 422


class TestListTags:
    async def test_list_and_search(self, client: AsyncClient) -> None:
        cid = await _make_collection(client, "TagCol-6")
        await client.post(f"/api/v1/collections/{cid}/tags", json={"key": "kinase"})
        await client.post(f"/api/v1/collections/{cid}/tags", json={"key": "solubility"})
        all_resp = await client.get("/api/v1/tags")
        assert all_resp.status_code == 200
        keys = {t["key"] for t in all_resp.json()}
        assert {"kinase", "solubility"} <= keys
        kin = await client.get("/api/v1/tags", params={"q": "kin"})
        assert {t["key"] for t in kin.json()} == {"kinase"}

    async def test_mine_filter(self, client: AsyncClient) -> None:
        cid = await _make_collection(client, "TagCol-7")
        await client.post(f"/api/v1/collections/{cid}/tags", json={"key": "mine-tag"})
        resp = await client.get("/api/v1/tags", params={"mine": "true"})
        assert resp.status_code == 200
        assert any(t["key"] == "mine-tag" for t in resp.json())


class TestAuth:
    async def test_viewer_cannot_assign_403(
        self, client: AsyncClient, viewer_client: AsyncClient
    ) -> None:
        cid = await _make_collection(client, "TagCol-8")  # admin creates the collection
        resp = await viewer_client.post(
            f"/api/v1/collections/{cid}/tags", json={"key": "x"}
        )
        assert resp.status_code == 403

    async def test_viewer_can_read(
        self, client: AsyncClient, viewer_client: AsyncClient
    ) -> None:
        cid = await _make_collection(client, "TagCol-9")
        await client.post(f"/api/v1/collections/{cid}/tags", json={"key": "readable"})
        resp = await viewer_client.get(f"/api/v1/collections/{cid}/tags")
        assert resp.status_code == 200
        assert [t["key"] for t in resp.json()] == ["readable"]
