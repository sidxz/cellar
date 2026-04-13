"""API tests for PlateTemplate endpoints."""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient


class TestCreatePlateTemplate:
    async def test_create_success(self, client: AsyncClient) -> None:
        resp = await client.post(
            "/api/v1/plate-templates",
            json={
                "name": "Standard 96-well",
                "format": "96",
                "template_map": {"A1": "compound", "A2": "positive_control"},
                "description": "Default screening layout",
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "Standard 96-well"
        assert data["format"] == "96"
        assert data["template_map"] == {"A1": "compound", "A2": "positive_control"}
        assert data["description"] == "Default screening layout"
        assert "id" in data
        assert "workspace_id" in data
        assert "created_by" in data

    async def test_create_minimal(self, client: AsyncClient) -> None:
        resp = await client.post(
            "/api/v1/plate-templates",
            json={
                "name": "Empty 384",
                "format": "384",
                "template_map": {},
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "Empty 384"
        assert data["format"] == "384"
        assert data["description"] is None

    async def test_create_empty_name_422(self, client: AsyncClient) -> None:
        resp = await client.post(
            "/api/v1/plate-templates",
            json={
                "name": "",
                "format": "96",
                "template_map": {},
            },
        )
        assert resp.status_code == 422


class TestListPlateTemplates:
    async def test_empty_list(self, client: AsyncClient) -> None:
        resp = await client.get("/api/v1/plate-templates")
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_list_after_create(self, client: AsyncClient) -> None:
        await client.post(
            "/api/v1/plate-templates",
            json={"name": "Template A", "format": "96", "template_map": {"A1": "sample"}},
        )
        await client.post(
            "/api/v1/plate-templates",
            json={"name": "Template B", "format": "384", "template_map": {}},
        )
        resp = await client.get("/api/v1/plate-templates")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        names = {t["name"] for t in data}
        assert names == {"Template A", "Template B"}


class TestGetPlateTemplate:
    async def test_get_success(self, client: AsyncClient) -> None:
        create = await client.post(
            "/api/v1/plate-templates",
            json={"name": "Get Test", "format": "96", "template_map": {"B3": "blank"}},
        )
        template_id = create.json()["id"]
        resp = await client.get(f"/api/v1/plate-templates/{template_id}")
        assert resp.status_code == 200
        assert resp.json()["name"] == "Get Test"
        assert resp.json()["template_map"] == {"B3": "blank"}

    async def test_get_not_found_404(self, client: AsyncClient) -> None:
        resp = await client.get(f"/api/v1/plate-templates/{uuid.uuid4()}")
        assert resp.status_code == 404


class TestUpdatePlateTemplate:
    async def test_update_name(self, client: AsyncClient) -> None:
        create = await client.post(
            "/api/v1/plate-templates",
            json={"name": "Old Name", "format": "96", "template_map": {}},
        )
        template_id = create.json()["id"]
        resp = await client.patch(
            f"/api/v1/plate-templates/{template_id}",
            json={"name": "New Name"},
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "New Name"
        assert resp.json()["format"] == "96"  # unchanged

    async def test_update_not_found_404(self, client: AsyncClient) -> None:
        resp = await client.patch(
            f"/api/v1/plate-templates/{uuid.uuid4()}",
            json={"name": "Whatever"},
        )
        assert resp.status_code == 404

    async def test_update_template_map(self, client: AsyncClient) -> None:
        create = await client.post(
            "/api/v1/plate-templates",
            json={"name": "Map Test", "format": "96", "template_map": {"A1": "sample"}},
        )
        template_id = create.json()["id"]
        resp = await client.patch(
            f"/api/v1/plate-templates/{template_id}",
            json={"template_map": {"A1": "blank", "A2": "sample"}},
        )
        assert resp.status_code == 200
        assert resp.json()["template_map"] == {"A1": "blank", "A2": "sample"}


class TestDeletePlateTemplate:
    async def test_delete_success(self, client: AsyncClient) -> None:
        create = await client.post(
            "/api/v1/plate-templates",
            json={"name": "To Delete", "format": "96", "template_map": {}},
        )
        template_id = create.json()["id"]

        resp = await client.delete(f"/api/v1/plate-templates/{template_id}")
        assert resp.status_code == 204

        # Verify gone
        get_resp = await client.get(f"/api/v1/plate-templates/{template_id}")
        assert get_resp.status_code == 404

    async def test_delete_not_found_404(self, client: AsyncClient) -> None:
        resp = await client.delete(f"/api/v1/plate-templates/{uuid.uuid4()}")
        assert resp.status_code == 404
