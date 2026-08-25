"""API tests for /api/v1/plate-groups."""

from __future__ import annotations

import json
import uuid

from httpx import AsyncClient

from tests.api.conftest import AUTH_ORG_ID, OTHER_ORG_ID


async def _mk_group(client: AsyncClient, name: str, **overrides) -> dict:
    body = {"name": name, **overrides}
    resp = await client.post("/api/v1/plate-groups", json=body)
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _mk_plate(client: AsyncClient, barcode: str, **overrides) -> dict:
    body = {
        "barcode": barcode,
        "plate_label": barcode,
        "format": "96",
        "plate_type": "assay",
        **overrides,
    }
    resp = await client.post("/api/v1/plates", json=body)
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _mk_location(client: AsyncClient, name: str) -> dict:
    resp = await client.post("/api/v1/storage-locations", json={"name": name, "type": "site"})
    assert resp.status_code == 201, resp.text
    return resp.json()


class TestCreate:
    async def test_create_defaults_to_caller_org(self, client: AsyncClient) -> None:
        g = await _mk_group(client, f"G-{uuid.uuid4().hex[:6]}")
        assert g["owner_org_id"] == str(AUTH_ORG_ID)
        assert g["parent_group_id"] is None
        assert g["version"] == 1

    async def test_editor_cannot_create_for_foreign_org(
        self, editor_client_own_org: AsyncClient
    ) -> None:
        resp = await editor_client_own_org.post(
            "/api/v1/plate-groups",
            json={"name": "X", "owner_org_id": str(uuid.uuid4())},
        )
        assert resp.status_code == 403

    async def test_admin_can_create_for_foreign_org(self, client: AsyncClient) -> None:
        g = await _mk_group(
            client, f"G-{uuid.uuid4().hex[:6]}", owner_org_id=str(OTHER_ORG_ID)
        )
        assert g["owner_org_id"] == str(OTHER_ORG_ID)

    async def test_viewer_forbidden(self, viewer_client: AsyncClient) -> None:
        resp = await viewer_client.post("/api/v1/plate-groups", json={"name": "X"})
        assert resp.status_code == 403

    async def test_duplicate_root_name_conflict(self, client: AsyncClient) -> None:
        name = f"Dup-{uuid.uuid4().hex[:6]}"
        await _mk_group(client, name)
        resp = await client.post("/api/v1/plate-groups", json={"name": name})
        assert resp.status_code == 409

    async def test_parent_in_other_org_rejected(self, client: AsyncClient) -> None:
        parent = await _mk_group(
            client, f"P-{uuid.uuid4().hex[:6]}", owner_org_id=str(OTHER_ORG_ID)
        )
        resp = await client.post(
            "/api/v1/plate-groups",
            json={"name": "child", "parent_group_id": parent["id"]},
            # admin's own org (default) != parent's org
        )
        assert resp.status_code == 422


class TestUpdateMoveDelete:
    async def test_rename_and_clear_type(self, client: AsyncClient) -> None:
        g = await _mk_group(client, f"G-{uuid.uuid4().hex[:6]}", group_type="vendor")
        resp = await client.patch(
            f"/api/v1/plate-groups/{g['id']}",
            json={"name": "Renamed", "group_type": None},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["name"] == "Renamed"
        assert resp.json()["group_type"] is None

    async def test_move_and_cycle_rejected(self, client: AsyncClient) -> None:
        root = await _mk_group(client, f"R-{uuid.uuid4().hex[:6]}")
        child = await _mk_group(
            client, f"C-{uuid.uuid4().hex[:6]}", parent_group_id=root["id"]
        )
        # Move root under its own child -> cycle
        resp = await client.post(
            f"/api/v1/plate-groups/{root['id']}/move",
            json={"parent_group_id": child["id"]},
        )
        assert resp.status_code == 422
        # Move child to root level
        resp = await client.post(
            f"/api/v1/plate-groups/{child['id']}/move", json={"parent_group_id": None}
        )
        assert resp.status_code == 200
        assert resp.json()["parent_group_id"] is None

    async def test_delete_with_children_conflict_then_ok(self, client: AsyncClient) -> None:
        root = await _mk_group(client, f"R-{uuid.uuid4().hex[:6]}")
        child = await _mk_group(
            client, f"C-{uuid.uuid4().hex[:6]}", parent_group_id=root["id"]
        )
        resp = await client.delete(f"/api/v1/plate-groups/{root['id']}")
        assert resp.status_code == 409
        assert (await client.delete(f"/api/v1/plate-groups/{child['id']}")).status_code == 204
        assert (await client.delete(f"/api/v1/plate-groups/{root['id']}")).status_code == 204

    async def test_delete_ungroups_plates(self, client: AsyncClient) -> None:
        g = await _mk_group(client, f"G-{uuid.uuid4().hex[:6]}")
        plate = await _mk_plate(client, f"PL-{uuid.uuid4().hex[:8]}")
        resp = await client.post(
            f"/api/v1/plate-groups/{g['id']}/plates", json={"plate_ids": [plate["id"]]}
        )
        assert resp.status_code == 204, resp.text
        assert (await client.delete(f"/api/v1/plate-groups/{g['id']}")).status_code == 204
        got = await client.get(f"/api/v1/plates/{plate['id']}")
        assert got.status_code == 200
        assert got.json()["group_id"] is None


class TestTree:
    async def test_tree_shape_and_counts(self, client: AsyncClient) -> None:
        tag = uuid.uuid4().hex[:6]
        root = await _mk_group(client, f"Root-{tag}")
        child = await _mk_group(client, f"Child-{tag}", parent_group_id=root["id"])
        plate = await _mk_plate(client, f"PL-{uuid.uuid4().hex[:8]}")
        await client.post(
            f"/api/v1/plate-groups/{child['id']}/plates", json={"plate_ids": [plate["id"]]}
        )
        resp = await client.get("/api/v1/plate-groups/tree")
        assert resp.status_code == 200, resp.text
        tree = resp.json()
        assert tree["org_id"] == str(AUTH_ORG_ID)
        roots = {n["name"]: n for n in tree["roots"]}
        node = roots[f"Root-{tag}"]
        assert node["plate_count"] == 0
        (child_node,) = [c for c in node["children"] if c["name"] == f"Child-{tag}"]
        assert child_node["plate_count"] == 1

    async def test_tree_scoped_to_requested_org(self, client: AsyncClient) -> None:
        mine = await _mk_group(client, f"Mine-{uuid.uuid4().hex[:6]}")
        theirs = await _mk_group(
            client, f"Theirs-{uuid.uuid4().hex[:6]}", owner_org_id=str(OTHER_ORG_ID)
        )
        resp = await client.get(f"/api/v1/plate-groups/tree?org_id={OTHER_ORG_ID}")
        assert resp.status_code == 200
        names = [n["name"] for n in resp.json()["roots"]]
        assert theirs["name"] in names
        assert mine["name"] not in names

    async def test_foreign_org_tree_forbidden_for_editor_ok_for_admin_and_member(
        self,
        client: AsyncClient,
        editor_client_own_org: AsyncClient,
        editor_client_other_org: AsyncClient,
    ) -> None:
        await _mk_group(client, f"Frn-{uuid.uuid4().hex[:6]}", owner_org_id=str(OTHER_ORG_ID))
        # Editor of another org -> 403 (org existence is public, contents are not)
        resp = await editor_client_own_org.get(f"/api/v1/plate-groups/tree?org_id={OTHER_ORG_ID}")
        assert resp.status_code == 403
        # Workspace admin -> bypass
        resp = await client.get(f"/api/v1/plate-groups/tree?org_id={OTHER_ORG_ID}")
        assert resp.status_code == 200
        # Member still sees it
        resp = await editor_client_other_org.get(
            f"/api/v1/plate-groups/tree?org_id={OTHER_ORG_ID}"
        )
        assert resp.status_code == 200


class TestAssignRemove:
    async def test_assign_org_mismatch_rejected(self, client: AsyncClient) -> None:
        g = await _mk_group(client, f"G-{uuid.uuid4().hex[:6]}")  # AUTH_ORG
        plate = await _mk_plate(
            client, f"PL-{uuid.uuid4().hex[:8]}", owner_org_id=str(OTHER_ORG_ID)
        )
        resp = await client.post(
            f"/api/v1/plate-groups/{g['id']}/plates", json={"plate_ids": [plate["id"]]}
        )
        assert resp.status_code == 422

    async def test_assign_then_remove_and_list_filter(self, client: AsyncClient) -> None:
        g = await _mk_group(client, f"G-{uuid.uuid4().hex[:6]}")
        plate = await _mk_plate(client, f"PL-{uuid.uuid4().hex[:8]}")
        assert (
            await client.post(
                f"/api/v1/plate-groups/{g['id']}/plates", json={"plate_ids": [plate["id"]]}
            )
        ).status_code == 204
        listed = await client.get(f"/api/v1/plates?group_id={g['id']}")
        assert [p["id"] for p in listed.json()] == [plate["id"]]
        got = await client.get(f"/api/v1/plates/{plate['id']}")
        assert got.json()["group_id"] == g["id"]
        assert (
            await client.request(
                "DELETE",
                f"/api/v1/plate-groups/{g['id']}/plates",
                json={"plate_ids": [plate["id"]]},
            )
        ).status_code == 204
        assert (await client.get(f"/api/v1/plates?group_id={g['id']}")).json() == []

    async def test_remove_plate_not_in_group_rejected(self, client: AsyncClient) -> None:
        g = await _mk_group(client, f"G-{uuid.uuid4().hex[:6]}")
        plate = await _mk_plate(client, f"PL-{uuid.uuid4().hex[:8]}")
        resp = await client.request(
            "DELETE",
            f"/api/v1/plate-groups/{g['id']}/plates",
            json={"plate_ids": [plate["id"]]},
        )
        assert resp.status_code == 422

    async def test_hidden_group_404s_for_other_org(
        self, client: AsyncClient, editor_client_own_org: AsyncClient
    ) -> None:
        g = await _mk_group(
            client, f"Frn-{uuid.uuid4().hex[:6]}", owner_org_id=str(OTHER_ORG_ID)
        )
        # AUTH_ORG editor: foreign-org group is indistinguishable from missing.
        resp = await editor_client_own_org.patch(
            f"/api/v1/plate-groups/{g['id']}", json={"name": "nope"}
        )
        assert resp.status_code == 404
        resp = await editor_client_own_org.request("DELETE", f"/api/v1/plate-groups/{g['id']}")
        assert resp.status_code == 404


class TestMetadata:
    async def test_create_round_trips_metadata_into_tree(self, client: AsyncClient) -> None:
        g = await _mk_group(
            client,
            f"Meta-{uuid.uuid4().hex[:6]}",
            state="Solubilized",
            initial_volume_ul=55.0,
            initial_concentration_mm=10.0,
            compound_count=17606,
            scientist="Jane Doe",
        )
        assert g["state"] == "Solubilized"
        assert g["compound_count"] == 17606
        assert g["created_at"]
        tree = (await client.get("/api/v1/plate-groups/tree")).json()
        node = next(r for r in tree["roots"] if r["id"] == g["id"])
        assert node["scientist"] == "Jane Doe"
        assert node["initial_volume_ul"] == 55.0
        assert node["plate_format"] is None

    async def test_patch_partial_keeps_others_and_null_clears(self, client: AsyncClient) -> None:
        g = await _mk_group(client, f"Meta-{uuid.uuid4().hex[:6]}", state="Dry", scientist="Jane")
        resp = await client.patch(f"/api/v1/plate-groups/{g['id']}", json={"state": "Retired"})
        assert resp.status_code == 200, resp.text
        assert resp.json()["state"] == "Retired"
        assert resp.json()["scientist"] == "Jane"
        resp = await client.patch(f"/api/v1/plate-groups/{g['id']}", json={"scientist": None})
        assert resp.status_code == 200, resp.text
        assert resp.json()["scientist"] is None
        assert resp.json()["state"] == "Retired"

    async def test_negative_measurement_rejected(self, client: AsyncClient) -> None:
        resp = await client.post(
            "/api/v1/plate-groups",
            json={"name": f"Bad-{uuid.uuid4().hex[:6]}", "initial_volume_ul": -1},
        )
        assert resp.status_code == 422, resp.text

    async def test_nan_measurement_rejected(self, client: AsyncClient) -> None:
        resp = await client.post(
            "/api/v1/plate-groups",
            content=json.dumps(
                {"name": f"Bad-{uuid.uuid4().hex[:6]}", "initial_volume_ul": float("nan")}
            ),
            headers={"Content-Type": "application/json"},
        )
        assert resp.status_code == 422, resp.text

    async def test_create_with_nonexistent_storage_location_404s(
        self, client: AsyncClient
    ) -> None:
        resp = await client.post(
            "/api/v1/plate-groups",
            json={
                "name": f"Loc-{uuid.uuid4().hex[:6]}",
                "storage_location_id": str(uuid.uuid4()),
            },
        )
        assert resp.status_code == 404, resp.text

    async def test_patch_with_nonexistent_storage_location_404s(
        self, client: AsyncClient
    ) -> None:
        g = await _mk_group(client, f"Meta-{uuid.uuid4().hex[:6]}")
        resp = await client.patch(
            f"/api/v1/plate-groups/{g['id']}",
            json={"storage_location_id": str(uuid.uuid4())},
        )
        assert resp.status_code == 404, resp.text

    async def test_create_with_real_storage_location_round_trips(
        self, client: AsyncClient
    ) -> None:
        loc = await _mk_location(client, f"Room-{uuid.uuid4().hex[:6]}")
        g = await _mk_group(
            client, f"Loc-{uuid.uuid4().hex[:6]}", storage_location_id=loc["id"]
        )
        assert g["storage_location_id"] == loc["id"]
        tree = (await client.get("/api/v1/plate-groups/tree")).json()
        node = next(r for r in tree["roots"] if r["id"] == g["id"])
        assert node["storage_location_id"] == loc["id"]

    async def test_tree_plate_format_single_and_mixed(self, client: AsyncClient) -> None:
        single = await _mk_group(client, f"Single-{uuid.uuid4().hex[:6]}")
        mixed = await _mk_group(client, f"Mixed-{uuid.uuid4().hex[:6]}")
        p1 = await _mk_plate(client, f"PL-{uuid.uuid4().hex[:8]}", format="96")
        p2 = await _mk_plate(client, f"PL-{uuid.uuid4().hex[:8]}", format="96")
        p3 = await _mk_plate(client, f"PL-{uuid.uuid4().hex[:8]}", format="384")
        for gid, ids in ((single["id"], [p1["id"]]), (mixed["id"], [p2["id"], p3["id"]])):
            r = await client.post(f"/api/v1/plate-groups/{gid}/plates", json={"plate_ids": ids})
            assert r.status_code == 204, r.text
        tree = (await client.get("/api/v1/plate-groups/tree")).json()
        by_id = {r["id"]: r for r in tree["roots"]}
        assert by_id[single["id"]]["plate_format"] == "96"
        assert by_id[mixed["id"]]["plate_format"] == "mixed"
