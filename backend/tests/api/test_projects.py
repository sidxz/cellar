"""API tests for project endpoints."""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient


class TestListProjects:
    async def test_empty_list(self, client: AsyncClient) -> None:
        resp = await client.get("/api/v1/projects")
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_list_after_create(self, client: AsyncClient) -> None:
        await client.post(
            "/api/v1/projects",
            json={"name": "Kinase Screening"},
        )
        resp = await client.get("/api/v1/projects")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["name"] == "Kinase Screening"


class TestCreateProject:
    async def test_create_success(self, client: AsyncClient) -> None:
        resp = await client.post(
            "/api/v1/projects",
            json={"name": "GPCR Discovery", "description": "GPCR target family"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "GPCR Discovery"
        assert data["description"] == "GPCR target family"
        assert data["status"] == "active"
        assert data["version"] == 1
        assert "id" in data
        assert "workspace_id" in data
        assert "created_by" in data

    async def test_create_minimal(self, client: AsyncClient) -> None:
        resp = await client.post(
            "/api/v1/projects",
            json={"name": "Minimal Project"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "Minimal Project"
        assert data["description"] is None

    async def test_create_duplicate_name_409(self, client: AsyncClient) -> None:
        await client.post(
            "/api/v1/projects",
            json={"name": "Unique Project"},
        )
        resp = await client.post(
            "/api/v1/projects",
            json={"name": "Unique Project"},
        )
        assert resp.status_code == 409
        assert "already exists" in resp.json()["message"]

    async def test_create_empty_name_422(self, client: AsyncClient) -> None:
        resp = await client.post(
            "/api/v1/projects",
            json={"name": ""},
        )
        assert resp.status_code == 422


class TestGetProject:
    async def test_get_success(self, client: AsyncClient) -> None:
        create = await client.post(
            "/api/v1/projects",
            json={"name": "GetTest Project"},
        )
        project_id = create.json()["id"]
        resp = await client.get(f"/api/v1/projects/{project_id}")
        assert resp.status_code == 200
        assert resp.json()["name"] == "GetTest Project"

    async def test_get_not_found_404(self, client: AsyncClient) -> None:
        resp = await client.get(f"/api/v1/projects/{uuid.uuid4()}")
        assert resp.status_code == 404


class TestUpdateProject:
    async def test_update_name(self, client: AsyncClient) -> None:
        create = await client.post(
            "/api/v1/projects",
            json={"name": "Old Name", "description": "original"},
        )
        project_id = create.json()["id"]
        resp = await client.patch(
            f"/api/v1/projects/{project_id}",
            json={"name": "New Name"},
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "New Name"
        assert resp.json()["description"] == "original"  # unchanged
        assert resp.json()["version"] == 2

    async def test_update_not_found_404(self, client: AsyncClient) -> None:
        resp = await client.patch(
            f"/api/v1/projects/{uuid.uuid4()}",
            json={"name": "Whatever"},
        )
        assert resp.status_code == 404


class TestArchiveProject:
    async def test_archive_success(self, client: AsyncClient) -> None:
        create = await client.post(
            "/api/v1/projects",
            json={"name": "To Archive"},
        )
        project_id = create.json()["id"]
        resp = await client.post(f"/api/v1/projects/{project_id}/archive")
        assert resp.status_code == 200
        assert resp.json()["status"] == "archived"

    async def test_archive_already_archived_422(self, client: AsyncClient) -> None:
        create = await client.post(
            "/api/v1/projects",
            json={"name": "Already Archived"},
        )
        project_id = create.json()["id"]
        await client.post(f"/api/v1/projects/{project_id}/archive")
        resp = await client.post(f"/api/v1/projects/{project_id}/archive")
        assert resp.status_code == 422

    async def test_update_after_archive_422(self, client: AsyncClient) -> None:
        create = await client.post(
            "/api/v1/projects",
            json={"name": "Frozen Project"},
        )
        project_id = create.json()["id"]
        await client.post(f"/api/v1/projects/{project_id}/archive")
        resp = await client.patch(
            f"/api/v1/projects/{project_id}",
            json={"name": "Should Fail"},
        )
        assert resp.status_code == 422
