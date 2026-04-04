"""API tests for controlled vocabulary endpoints."""

from __future__ import annotations

import uuid

from httpx import AsyncClient


class TestListVocabularies:
    async def test_empty_list(self, client: AsyncClient) -> None:
        resp = await client.get("/api/v1/vocabularies")
        assert resp.status_code == 200
        assert resp.json() == []


class TestCreateVocabulary:
    async def test_create_with_terms(self, client: AsyncClient) -> None:
        resp = await client.post(
            "/api/v1/vocabularies",
            json={"name": "Species", "terms": ["Human", "Mouse", "Rat"]},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "Species"
        assert data["terms"] == ["Human", "Mouse", "Rat"]
        assert data["is_locked"] is False
        assert "id" in data
        assert "created_by" in data

    async def test_create_without_terms(self, client: AsyncClient) -> None:
        resp = await client.post(
            "/api/v1/vocabularies",
            json={"name": "Empty List"},
        )
        assert resp.status_code == 201
        assert resp.json()["terms"] == []

    async def test_create_duplicate_name_409(self, client: AsyncClient) -> None:
        await client.post(
            "/api/v1/vocabularies",
            json={"name": "Duplicate"},
        )
        resp = await client.post(
            "/api/v1/vocabularies",
            json={"name": "Duplicate"},
        )
        assert resp.status_code == 409

    async def test_create_empty_name_422(self, client: AsyncClient) -> None:
        resp = await client.post(
            "/api/v1/vocabularies",
            json={"name": ""},
        )
        assert resp.status_code == 422


class TestUpdateVocabulary:
    async def test_update_terms(self, client: AsyncClient) -> None:
        create = await client.post(
            "/api/v1/vocabularies",
            json={"name": "Routes", "terms": ["IV", "Oral"]},
        )
        vid = create.json()["id"]
        resp = await client.patch(
            f"/api/v1/vocabularies/{vid}",
            json={"terms": ["IV", "Oral", "Topical"]},
        )
        assert resp.status_code == 200
        assert resp.json()["terms"] == ["IV", "Oral", "Topical"]
        assert resp.json()["version"] == 2

    async def test_rename(self, client: AsyncClient) -> None:
        create = await client.post(
            "/api/v1/vocabularies",
            json={"name": "OldVocab"},
        )
        vid = create.json()["id"]
        resp = await client.patch(
            f"/api/v1/vocabularies/{vid}",
            json={"name": "NewVocab"},
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "NewVocab"

    async def test_lock(self, client: AsyncClient) -> None:
        create = await client.post(
            "/api/v1/vocabularies",
            json={"name": "Lockable"},
        )
        vid = create.json()["id"]
        resp = await client.patch(
            f"/api/v1/vocabularies/{vid}",
            json={"is_locked": True},
        )
        assert resp.status_code == 200
        assert resp.json()["is_locked"] is True

    async def test_update_not_found_404(self, client: AsyncClient) -> None:
        resp = await client.patch(
            f"/api/v1/vocabularies/{uuid.uuid4()}",
            json={"name": "Nope"},
        )
        assert resp.status_code == 404

    async def test_rename_to_duplicate_409(self, client: AsyncClient) -> None:
        await client.post("/api/v1/vocabularies", json={"name": "Taken"})
        create2 = await client.post("/api/v1/vocabularies", json={"name": "Other"})
        vid = create2.json()["id"]
        resp = await client.patch(
            f"/api/v1/vocabularies/{vid}",
            json={"name": "Taken"},
        )
        assert resp.status_code == 409


class TestDeleteVocabulary:
    async def test_delete_success(self, client: AsyncClient) -> None:
        create = await client.post(
            "/api/v1/vocabularies",
            json={"name": "Deletable"},
        )
        vid = create.json()["id"]
        resp = await client.delete(f"/api/v1/vocabularies/{vid}")
        assert resp.status_code == 204

        # Verify it's gone
        list_resp = await client.get("/api/v1/vocabularies")
        assert all(v["id"] != vid for v in list_resp.json())

    async def test_delete_not_found_404(self, client: AsyncClient) -> None:
        resp = await client.delete(f"/api/v1/vocabularies/{uuid.uuid4()}")
        assert resp.status_code == 404

    async def test_delete_locked_422(self, client: AsyncClient) -> None:
        create = await client.post(
            "/api/v1/vocabularies",
            json={"name": "LockedVocab"},
        )
        vid = create.json()["id"]
        # Lock it
        await client.patch(f"/api/v1/vocabularies/{vid}", json={"is_locked": True})
        # Try to delete
        resp = await client.delete(f"/api/v1/vocabularies/{vid}")
        assert resp.status_code == 422
        assert "locked" in resp.json()["message"].lower()
