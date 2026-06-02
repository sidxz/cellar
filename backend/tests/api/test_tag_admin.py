"""API tests for admin tag operations (rename/merge/delete + auth)."""

from __future__ import annotations

import uuid

from httpx import AsyncClient


async def _collection(client: AsyncClient, name: str) -> str:
    resp = await client.post("/api/v1/collections", json={"name": name})
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def _tag_collection(client: AsyncClient, cid: str, key: str, value=None) -> str:
    resp = await client.post(
        f"/api/v1/collections/{cid}/tags", json={"key": key, "value": value}
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


class TestRename:
    async def test_rename(self, client: AsyncClient) -> None:
        cid = await _collection(client, "AdminCol-1")
        tid = await _tag_collection(client, cid, "oldname")
        resp = await client.patch(f"/api/v1/tags/{tid}", json={"key": "newname"})
        assert resp.status_code == 200
        assert resp.json()["key"] == "newname"

    async def test_rename_collision_409(self, client: AsyncClient) -> None:
        cid = await _collection(client, "AdminCol-2")
        await _tag_collection(client, cid, "taken")
        tid = await _tag_collection(client, cid, "other")
        resp = await client.patch(f"/api/v1/tags/{tid}", json={"key": "taken"})
        assert resp.status_code == 409


class TestMerge:
    async def test_merge(self, client: AsyncClient) -> None:
        cid = await _collection(client, "AdminCol-3")
        src = await _tag_collection(client, cid, "source")
        tgt = await _tag_collection(client, cid, "target")
        resp = await client.post(f"/api/v1/tags/{src}/merge", json={"target_tag_id": tgt})
        assert resp.status_code == 200
        assert resp.json()["id"] == tgt
        got = await client.get(f"/api/v1/collections/{cid}/tags")
        keys = {t["key"] for t in got.json()}
        assert keys == {"target"}


class TestDelete:
    async def test_delete(self, client: AsyncClient) -> None:
        cid = await _collection(client, "AdminCol-4")
        tid = await _tag_collection(client, cid, "doomed")
        resp = await client.delete(f"/api/v1/tags/{tid}")
        assert resp.status_code == 204
        got = await client.get(f"/api/v1/collections/{cid}/tags")
        assert got.json() == []

    async def test_delete_not_found_404(self, client: AsyncClient) -> None:
        resp = await client.delete(f"/api/v1/tags/{uuid.uuid4()}")
        assert resp.status_code == 404


class TestAuth:
    async def test_editor_cannot_rename_403(
        self, client: AsyncClient, editor_client: AsyncClient
    ) -> None:
        cid = await _collection(client, "AdminCol-5")
        tid = await _tag_collection(client, cid, "x")
        resp = await editor_client.patch(f"/api/v1/tags/{tid}", json={"key": "y"})
        assert resp.status_code == 403

    async def test_editor_cannot_delete_403(
        self, client: AsyncClient, editor_client: AsyncClient
    ) -> None:
        cid = await _collection(client, "AdminCol-6")
        tid = await _tag_collection(client, cid, "x")
        resp = await editor_client.delete(f"/api/v1/tags/{tid}")
        assert resp.status_code == 403
