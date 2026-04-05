"""API tests for saved-search endpoints."""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient


class TestCreateSavedSearch:
    async def test_create_success(self, client: AsyncClient) -> None:
        resp = await client.post(
            "/api/v1/saved-searches",
            json={
                "name": "Active Compounds",
                "query": {"structure_type": "substructure", "smarts": "c1ccccc1"},
                "columns": {"name": True, "smiles": True},
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "Active Compounds"
        assert data["query"] == {"structure_type": "substructure", "smarts": "c1ccccc1"}
        assert data["columns"] == {"name": True, "smiles": True}
        assert data["visibility"] == "private"
        assert data["project_id"] is None
        assert data["version"] == 1
        assert "id" in data

    async def test_create_project_visibility_with_project_id(
        self, client: AsyncClient
    ) -> None:
        proj = await client.post("/api/v1/projects", json={"name": "SS Project"})
        project_id = proj.json()["id"]

        resp = await client.post(
            "/api/v1/saved-searches",
            json={
                "name": "Team Search",
                "query": {"name_contains": "aspirin"},
                "visibility": "project",
                "project_id": project_id,
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["visibility"] == "project"
        assert data["project_id"] == project_id

    async def test_create_project_visibility_without_project_id_422(
        self, client: AsyncClient
    ) -> None:
        resp = await client.post(
            "/api/v1/saved-searches",
            json={
                "name": "Bad Search",
                "query": {"name_contains": "test"},
                "visibility": "project",
            },
        )
        assert resp.status_code == 422


class TestListSavedSearches:
    async def test_list_all(self, client: AsyncClient) -> None:
        await client.post(
            "/api/v1/saved-searches",
            json={"name": "Search A", "query": {"a": 1}},
        )
        await client.post(
            "/api/v1/saved-searches",
            json={"name": "Search B", "query": {"b": 2}},
        )
        resp = await client.get("/api/v1/saved-searches")
        assert resp.status_code == 200
        assert len(resp.json()) == 2

    async def test_filter_by_mine(self, client: AsyncClient) -> None:
        await client.post(
            "/api/v1/saved-searches",
            json={"name": "My Search", "query": {"x": 1}},
        )
        resp = await client.get(
            "/api/v1/saved-searches", params={"mine": "true"}
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 1
        assert data[0]["name"] == "My Search"


class TestGetSavedSearch:
    async def test_get_success(self, client: AsyncClient) -> None:
        create = await client.post(
            "/api/v1/saved-searches",
            json={"name": "Fetch Me", "query": {"q": "test"}},
        )
        search_id = create.json()["id"]
        resp = await client.get(f"/api/v1/saved-searches/{search_id}")
        assert resp.status_code == 200
        assert resp.json()["name"] == "Fetch Me"

    async def test_get_not_found_404(self, client: AsyncClient) -> None:
        resp = await client.get(f"/api/v1/saved-searches/{uuid.uuid4()}")
        assert resp.status_code == 404


class TestUpdateSavedSearch:
    async def test_update_name(self, client: AsyncClient) -> None:
        create = await client.post(
            "/api/v1/saved-searches",
            json={"name": "Old SS", "query": {"q": "old"}},
        )
        search_id = create.json()["id"]
        resp = await client.patch(
            f"/api/v1/saved-searches/{search_id}",
            json={"name": "New SS"},
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "New SS"
        assert resp.json()["query"] == {"q": "old"}  # unchanged
        assert resp.json()["version"] == 2


class TestDeleteSavedSearch:
    async def test_delete_success(self, client: AsyncClient) -> None:
        create = await client.post(
            "/api/v1/saved-searches",
            json={"name": "Doomed SS", "query": {"x": 1}},
        )
        search_id = create.json()["id"]
        resp = await client.delete(f"/api/v1/saved-searches/{search_id}")
        assert resp.status_code == 204

        # Confirm it's gone
        get_resp = await client.get(f"/api/v1/saved-searches/{search_id}")
        assert get_resp.status_code == 404

    async def test_delete_not_found_404(self, client: AsyncClient) -> None:
        resp = await client.delete(f"/api/v1/saved-searches/{uuid.uuid4()}")
        assert resp.status_code == 404
