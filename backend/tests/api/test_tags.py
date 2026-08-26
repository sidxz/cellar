"""API tests for tagging endpoints (assignment uses collections — easy to create)."""

from __future__ import annotations

import uuid

from httpx import AsyncClient

from tests.api.conftest import OTHER_ORG_ID


async def _make_collection(client: AsyncClient, name: str) -> str:
    resp = await client.post("/api/v1/collections", json={"name": name})
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def _register_plate(client: AsyncClient, **overrides):
    body = {
        "barcode": f"PLT-{uuid.uuid4().hex[:8]}",
        "plate_label": "Test Plate",
        "format": "96",
        "plate_type": "assay",
    }
    body.update(overrides)
    return await client.post("/api/v1/plates", json=body)


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

    async def test_get_includes_assignment_provenance(self, client: AsyncClient) -> None:
        cid = await _make_collection(client, "TagCol-prov")
        await client.post(
            f"/api/v1/collections/{cid}/tags", json={"key": "Project", "value": "Alpha"}
        )
        got = await client.get(f"/api/v1/collections/{cid}/tags")
        assert got.status_code == 200, got.text
        row = got.json()[0]
        # Who/when THIS entity was tagged (assignment provenance), not the tag's own creation.
        assert row.get("assigned_by"), row
        assert row.get("assigned_at"), row
        uuid.UUID(row["assigned_by"])  # parses as a UUID

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


class TestPlateVisibility:
    """Per-entity plate tag routes gated by org-policy visibility (S2 Task 5c) —
    an invisible plate's tags 404 exactly like a missing plate's would."""

    async def test_get_and_assign_404_for_foreign_org(
        self,
        client: AsyncClient,
        editor_client_own_org: AsyncClient,
        editor_client_other_org: AsyncClient,
    ) -> None:
        reg = await _register_plate(client, owner_org_id=str(OTHER_ORG_ID))
        assert reg.status_code == 201, reg.text
        plate_id = reg.json()["id"]

        got = await editor_client_own_org.get(f"/api/v1/plates/{plate_id}/tags")
        assert got.status_code == 404, got.text

        assigned = await editor_client_own_org.post(
            f"/api/v1/plates/{plate_id}/tags", json={"key": "spam"}
        )
        assert assigned.status_code == 404, assigned.text

        # Own org unaffected.
        got_own = await editor_client_other_org.get(f"/api/v1/plates/{plate_id}/tags")
        assert got_own.status_code == 200, got_own.text
        assert got_own.json() == []

    async def test_set_and_unassign_404_for_foreign_org_200_for_own_org(
        self,
        client: AsyncClient,
        editor_client_own_org: AsyncClient,
        editor_client_other_org: AsyncClient,
    ) -> None:
        reg = await _register_plate(client, owner_org_id=str(OTHER_ORG_ID))
        assert reg.status_code == 201, reg.text
        plate_id = reg.json()["id"]

        # Own org tags it, so we have a real tag_id to probe DELETE with.
        tagged = await editor_client_other_org.post(
            f"/api/v1/plates/{plate_id}/tags", json={"key": "legit"}
        )
        assert tagged.status_code == 201, tagged.text
        tag_id = tagged.json()["id"]

        set_foreign = await editor_client_own_org.put(
            f"/api/v1/plates/{plate_id}/tags", json={"tags": [{"key": "spam"}]}
        )
        assert set_foreign.status_code == 404, set_foreign.text

        unassign_foreign = await editor_client_own_org.delete(
            f"/api/v1/plates/{plate_id}/tags/{tag_id}"
        )
        assert unassign_foreign.status_code == 404, unassign_foreign.text

        # Status quo preserved — the plate's own org can still read/write its tags.
        set_own = await editor_client_other_org.put(
            f"/api/v1/plates/{plate_id}/tags", json={"tags": [{"key": "legit"}, {"key": "extra"}]}
        )
        assert set_own.status_code == 200, set_own.text
        assert {t["key"] for t in set_own.json()} == {"legit", "extra"}
