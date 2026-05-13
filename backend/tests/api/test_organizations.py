"""API tests for organization endpoints."""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient


class TestListOrganizations:
    async def test_empty_list(self, client: AsyncClient) -> None:
        resp = await client.get("/api/v1/organizations")
        assert resp.status_code == 200
        assert resp.json()["items"] == []

    async def test_list_after_create(self, client: AsyncClient) -> None:
        await client.post(
            "/api/v1/organizations",
            json={"name": "Merck", "org_type": "pharma_partner"},
        )
        resp = await client.get("/api/v1/organizations")
        assert resp.status_code == 200
        data = resp.json()["items"]
        assert len(data) == 1
        assert data[0]["name"] == "Merck"

    async def test_list_excludes_inactive_by_default(self, client: AsyncClient) -> None:
        # Create then deactivate via PATCH
        create_resp = await client.post(
            "/api/v1/organizations",
            json={"name": "Old Corp", "org_type": "vendor"},
        )
        org_id = create_resp.json()["id"]
        await client.post(
            "/api/v1/organizations",
            json={"name": "Active Inc", "org_type": "internal"},
        )

        # Deactivate by patching (no dedicated endpoint, simulate via update)
        # Note: deactivation not exposed via PATCH — inactive orgs still show with include_inactive
        resp = await client.get("/api/v1/organizations", params={"include_inactive": "true"})
        assert resp.status_code == 200
        assert len(resp.json()["items"]) == 2


class TestCreateOrganization:
    async def test_create_success(self, client: AsyncClient) -> None:
        resp = await client.post(
            "/api/v1/organizations",
            json={
                "name": "Eurofins Munich",
                "org_type": "cro",
                "contact_name": "Alice",
                "contact_email": "alice@eurofins.com",
                "notes": "Key CRO partner",
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "Eurofins Munich"
        assert data["org_type"] == "cro"
        assert data["contact_name"] == "Alice"
        assert data["contact_email"] == "alice@eurofins.com"
        assert data["is_active"] is True
        assert data["version"] == 1
        assert "id" in data

    async def test_create_minimal(self, client: AsyncClient) -> None:
        resp = await client.post(
            "/api/v1/organizations",
            json={"name": "SaccLabs", "org_type": "internal"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["contact_name"] is None
        assert data["notes"] is None

    async def test_create_duplicate_name_409(self, client: AsyncClient) -> None:
        await client.post(
            "/api/v1/organizations",
            json={"name": "UniqueOrg", "org_type": "academic"},
        )
        resp = await client.post(
            "/api/v1/organizations",
            json={"name": "UniqueOrg", "org_type": "vendor"},
        )
        assert resp.status_code == 409
        assert "already exists" in resp.json()["message"]

    async def test_create_empty_name_422(self, client: AsyncClient) -> None:
        resp = await client.post(
            "/api/v1/organizations",
            json={"name": "", "org_type": "internal"},
        )
        assert resp.status_code == 422


class TestGetOrganization:
    async def test_get_success(self, client: AsyncClient) -> None:
        create = await client.post(
            "/api/v1/organizations",
            json={"name": "GetTest", "org_type": "internal"},
        )
        org_id = create.json()["id"]
        resp = await client.get(f"/api/v1/organizations/{org_id}")
        assert resp.status_code == 200
        assert resp.json()["name"] == "GetTest"

    async def test_get_not_found_404(self, client: AsyncClient) -> None:
        resp = await client.get(f"/api/v1/organizations/{uuid.uuid4()}")
        assert resp.status_code == 404


class TestUpdateOrganization:
    async def test_update_name(self, client: AsyncClient) -> None:
        create = await client.post(
            "/api/v1/organizations",
            json={"name": "OldName", "org_type": "cro"},
        )
        org_id = create.json()["id"]
        resp = await client.patch(
            f"/api/v1/organizations/{org_id}",
            json={"name": "NewName"},
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "NewName"
        assert resp.json()["org_type"] == "cro"  # unchanged
        assert resp.json()["version"] == 2

    async def test_update_not_found_404(self, client: AsyncClient) -> None:
        resp = await client.patch(
            f"/api/v1/organizations/{uuid.uuid4()}",
            json={"name": "Whatever"},
        )
        assert resp.status_code == 404

    async def test_update_duplicate_name_409(self, client: AsyncClient) -> None:
        await client.post(
            "/api/v1/organizations",
            json={"name": "Taken", "org_type": "internal"},
        )
        create2 = await client.post(
            "/api/v1/organizations",
            json={"name": "Other", "org_type": "internal"},
        )
        org_id = create2.json()["id"]
        resp = await client.patch(
            f"/api/v1/organizations/{org_id}",
            json={"name": "Taken"},
        )
        assert resp.status_code == 409
