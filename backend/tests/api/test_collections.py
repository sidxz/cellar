"""API tests for collection endpoints."""

from __future__ import annotations

import uuid

from httpx import AsyncClient


class TestCreateCollection:
    async def test_create_success(self, client: AsyncClient) -> None:
        # Create a project to link
        proj = await client.post(
            "/api/v1/projects", json={"name": "Host Project"}
        )
        project_id = proj.json()["id"]

        resp = await client.post(
            "/api/v1/collections",
            json={
                "name": "Hit List",
                "description": "Top screening hits",
                "project_id": project_id,
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "Hit List"
        assert data["description"] == "Top screening hits"
        assert data["project_id"] == project_id
        assert data["molecule_count"] == 0
        assert data["version"] == 1
        assert "id" in data

    async def test_create_minimal(self, client: AsyncClient) -> None:
        resp = await client.post(
            "/api/v1/collections",
            json={"name": "Bare Collection"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["description"] is None
        assert data["project_id"] is None
        assert data["owned_by_org_id"] is None


class TestGetCollection:
    async def test_get_includes_molecule_count(self, client: AsyncClient) -> None:
        create = await client.post(
            "/api/v1/collections", json={"name": "CountTest"}
        )
        coll_id = create.json()["id"]
        resp = await client.get(f"/api/v1/collections/{coll_id}")
        assert resp.status_code == 200
        assert resp.json()["molecule_count"] == 0

    async def test_get_includes_frozen_fields(self, client: AsyncClient) -> None:
        create = await client.post(
            "/api/v1/collections", json={"name": "FrozenFieldsTest"}
        )
        coll_id = create.json()["id"]
        resp = await client.get(f"/api/v1/collections/{coll_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["is_frozen"] is False
        assert data["derived_from_campaign_id"] is None

    async def test_get_not_found_404(self, client: AsyncClient) -> None:
        resp = await client.get(f"/api/v1/collections/{uuid.uuid4()}")
        assert resp.status_code == 404


class TestListCollections:
    async def test_list(self, client: AsyncClient) -> None:
        await client.post("/api/v1/collections", json={"name": "Col A"})
        await client.post("/api/v1/collections", json={"name": "Col B"})
        resp = await client.get("/api/v1/collections")
        assert resp.status_code == 200
        assert len(resp.json()["items"]) == 2

    async def test_filter_by_single_project(self, client: AsyncClient) -> None:
        proj = await client.post("/api/v1/projects", json={"name": "Filter Project"})
        project_id = proj.json()["id"]

        await client.post(
            "/api/v1/collections",
            json={"name": "In Project", "project_id": project_id},
        )
        await client.post(
            "/api/v1/collections", json={"name": "No Project"}
        )

        resp = await client.get(
            "/api/v1/collections", params={"project_ids": project_id}
        )
        assert resp.status_code == 200
        data = resp.json()["items"]
        assert len(data) == 1
        assert data[0]["name"] == "In Project"

    async def test_filter_by_multiple_projects_unions(self, client: AsyncClient) -> None:
        # Multi-project scoping: pickers should see the union when chemists
        # are working across two related programs.
        proj_a = await client.post("/api/v1/projects", json={"name": "Project A"})
        proj_b = await client.post("/api/v1/projects", json={"name": "Project B"})
        proj_c = await client.post("/api/v1/projects", json={"name": "Project C"})
        a_id = proj_a.json()["id"]
        b_id = proj_b.json()["id"]
        c_id = proj_c.json()["id"]

        await client.post(
            "/api/v1/collections",
            json={"name": "In A", "project_id": a_id},
        )
        await client.post(
            "/api/v1/collections",
            json={"name": "In B", "project_id": b_id},
        )
        await client.post(
            "/api/v1/collections",
            json={"name": "In C (excluded)", "project_id": c_id},
        )
        await client.post(
            "/api/v1/collections", json={"name": "Unscoped (excluded)"}
        )

        resp = await client.get(
            "/api/v1/collections",
            params=[("project_ids", a_id), ("project_ids", b_id)],
        )
        assert resp.status_code == 200
        names = sorted(c["name"] for c in resp.json()["items"])
        assert names == ["In A", "In B"]


class TestUpdateCollection:
    async def test_update_name(self, client: AsyncClient) -> None:
        create = await client.post(
            "/api/v1/collections", json={"name": "OldCol"}
        )
        coll_id = create.json()["id"]
        resp = await client.patch(
            f"/api/v1/collections/{coll_id}",
            json={"name": "NewCol"},
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "NewCol"
        assert resp.json()["version"] == 2


class TestDeleteCollection:
    async def test_delete_success(self, client: AsyncClient) -> None:
        create = await client.post(
            "/api/v1/collections", json={"name": "Doomed"}
        )
        coll_id = create.json()["id"]
        resp = await client.delete(f"/api/v1/collections/{coll_id}")
        assert resp.status_code == 204

        # Confirm it's gone
        get_resp = await client.get(f"/api/v1/collections/{coll_id}")
        assert get_resp.status_code == 404


class TestCollectionMolecules:
    async def test_list_molecules_empty(self, client: AsyncClient) -> None:
        create = await client.post(
            "/api/v1/collections", json={"name": "Empty Membership"}
        )
        coll_id = create.json()["id"]
        resp = await client.get(f"/api/v1/collections/{coll_id}/molecules")
        assert resp.status_code == 200
        assert resp.json() == []


class TestCollectionTypeAttribute:
    async def test_create_defaults_type_generic(self, client: AsyncClient) -> None:
        resp = await client.post("/api/v1/collections", json={"name": "Ad-hoc set"})
        assert resp.status_code == 201
        assert resp.json()["type"] == "generic"

    async def test_create_with_explicit_type(self, client: AsyncClient) -> None:
        resp = await client.post(
            "/api/v1/collections", json={"name": "Kinase Lib", "type": "library"}
        )
        assert resp.status_code == 201
        assert resp.json()["type"] == "library"

    async def test_patch_type(self, client: AsyncClient) -> None:
        created = await client.post("/api/v1/collections", json={"name": "X"})
        assert created.status_code == 201
        coll_id = created.json()["id"]

        resp = await client.patch(
            f"/api/v1/collections/{coll_id}", json={"type": "hit_list"}
        )
        assert resp.status_code == 200
        assert resp.json()["type"] == "hit_list"

    async def test_get_returns_type(self, client: AsyncClient) -> None:
        created = await client.post(
            "/api/v1/collections", json={"name": "Series set", "type": "series"}
        )
        coll_id = created.json()["id"]
        resp = await client.get(f"/api/v1/collections/{coll_id}")
        assert resp.status_code == 200
        assert resp.json()["type"] == "series"

    async def test_list_includes_type(self, client: AsyncClient) -> None:
        await client.post(
            "/api/v1/collections", json={"name": "Ref Set", "type": "reference_set"}
        )
        resp = await client.get("/api/v1/collections")
        assert resp.status_code == 200
        items = resp.json()["items"]
        assert len(items) == 1
        assert items[0]["type"] == "reference_set"

    async def test_invalid_type_returns_422(self, client: AsyncClient) -> None:
        resp = await client.post(
            "/api/v1/collections", json={"name": "Bad type", "type": "nonexistent"}
        )
        assert resp.status_code == 422

    async def test_patch_invalid_type_returns_422(self, client: AsyncClient) -> None:
        created = await client.post("/api/v1/collections", json={"name": "PatchBadType"})
        assert created.status_code == 201
        coll_id = created.json()["id"]

        resp = await client.patch(
            f"/api/v1/collections/{coll_id}", json={"type": "bogus"}
        )
        assert resp.status_code == 422

    async def test_patch_null_type_returns_422(self, client: AsyncClient) -> None:
        created = await client.post("/api/v1/collections", json={"name": "PatchNullType"})
        assert created.status_code == 201
        coll_id = created.json()["id"]

        resp = await client.patch(
            f"/api/v1/collections/{coll_id}", json={"type": None}
        )
        assert resp.status_code == 422
