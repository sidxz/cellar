"""API tests for the PlateGroup → Collection link (S16 §6).

Write validation on /plate-groups, name enrichment on tree/detail, the reverse
read GET /collections/{id}/plate-groups with loan counts, and the FK cascade.
"""

from __future__ import annotations

import uuid

from httpx import AsyncClient

from tests.api.conftest import OTHER_ORG_ID


async def _mk_collection(client: AsyncClient, name: str | None = None) -> dict:
    resp = await client.post(
        "/api/v1/collections", json={"name": name or f"Coll-{uuid.uuid4().hex[:6]}"}
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _mk_group(client: AsyncClient, name: str, **overrides) -> dict:
    resp = await client.post("/api/v1/plate-groups", json={"name": name, **overrides})
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _mk_plate(client: AsyncClient, group_id: str | None = None) -> dict:
    barcode = f"PL-{uuid.uuid4().hex[:8]}"
    resp = await client.post(
        "/api/v1/plates",
        json={"barcode": barcode, "plate_label": barcode, "format": "96", "plate_type": "assay"},
    )
    assert resp.status_code == 201, resp.text
    plate = resp.json()
    if group_id:
        r = await client.post(
            f"/api/v1/plate-groups/{group_id}/plates", json={"plate_ids": [plate["id"]]}
        )
        assert r.status_code == 204, r.text
    return plate


async def _mk_loan(client: AsyncClient, **body) -> dict:
    resp = await client.post("/api/v1/plate-loans", json=body)
    assert resp.status_code == 201, resp.text
    return resp.json()


class TestWrite:
    async def test_create_with_collection_carries_id_and_name(self, client: AsyncClient) -> None:
        coll = await _mk_collection(client)
        g = await _mk_group(client, f"G-{uuid.uuid4().hex[:6]}", collection_id=coll["id"])
        assert g["collection_id"] == coll["id"]
        assert g["collection_name"] == coll["name"]

    async def test_unknown_collection_404(self, client: AsyncClient) -> None:
        resp = await client.post(
            "/api/v1/plate-groups", json={"name": "X", "collection_id": str(uuid.uuid4())}
        )
        assert resp.status_code == 404

    async def test_update_sets_then_clears(self, client: AsyncClient) -> None:
        coll = await _mk_collection(client)
        g = await _mk_group(client, f"G-{uuid.uuid4().hex[:6]}")
        assert g["collection_id"] is None

        resp = await client.patch(
            f"/api/v1/plate-groups/{g['id']}", json={"collection_id": coll["id"]}
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["collection_name"] == coll["name"]

        resp = await client.patch(f"/api/v1/plate-groups/{g['id']}", json={"collection_id": None})
        assert resp.status_code == 200, resp.text
        assert resp.json()["collection_id"] is None
        assert resp.json()["collection_name"] is None

    async def test_update_unknown_collection_404(self, client: AsyncClient) -> None:
        g = await _mk_group(client, f"G-{uuid.uuid4().hex[:6]}")
        resp = await client.patch(
            f"/api/v1/plate-groups/{g['id']}", json={"collection_id": str(uuid.uuid4())}
        )
        assert resp.status_code == 404


class TestReadEnrichment:
    async def test_tree_and_detail_carry_names(self, client: AsyncClient) -> None:
        coll = await _mk_collection(client)
        tag = uuid.uuid4().hex[:6]
        root = await _mk_group(client, f"Root-{tag}", collection_id=coll["id"])
        child = await _mk_group(client, f"Child-{tag}", parent_group_id=root["id"])

        tree = (await client.get("/api/v1/plate-groups/tree")).json()
        node = next(n for n in tree["roots"] if n["id"] == root["id"])
        assert node["collection_id"] == coll["id"]
        assert node["collection_name"] == coll["name"]
        assert node["children"][0]["collection_id"] is None
        assert node["children"][0]["collection_name"] is None

        detail = (await client.get(f"/api/v1/plate-groups/{child['id']}")).json()
        assert detail["group"]["collection_name"] is None
        assert detail["ancestors"][0]["collection_id"] == coll["id"]
        assert detail["ancestors"][0]["collection_name"] == coll["name"]

        detail = (await client.get(f"/api/v1/plate-groups/{root['id']}")).json()
        assert detail["group"]["collection_name"] == coll["name"]
        assert detail["children"][0]["collection_name"] is None


class TestCollectionPlateGroups:
    async def test_linked_groups_with_counts(self, client: AsyncClient) -> None:
        coll = await _mk_collection(client)
        tag = uuid.uuid4().hex[:6]
        lib = await _mk_group(client, f"Lib-{tag}", group_type="library", collection_id=coll["id"])
        hits = await _mk_group(
            client, f"Set-{tag}", parent_group_id=lib["id"], collection_id=coll["id"]
        )
        await _mk_group(client, f"Unlinked-{tag}")  # no link → absent

        await _mk_plate(client, lib["id"])
        on_loan = await _mk_plate(client, hits["id"])
        overdue = await _mk_plate(client, hits["id"])
        await _mk_loan(client, plate_ids=[on_loan["id"]])
        await _mk_loan(client, plate_ids=[overdue["id"]], due_date="2020-01-01")

        resp = await client.get(f"/api/v1/collections/{coll['id']}/plate-groups")
        assert resp.status_code == 200, resp.text
        rows = resp.json()
        assert [r["group_id"] for r in rows] == [lib["id"], hits["id"]]  # ordered by path

        lib_row, set_row = rows
        assert lib_row["path"] == f"Lib-{tag}"
        assert lib_row["group_type"] == "library"
        assert lib_row["owner_org_id"] == lib["owner_org_id"]
        assert (lib_row["plate_count"], lib_row["subtree_plate_count"]) == (1, 3)
        assert (lib_row["on_loan_count"], lib_row["overdue_count"]) == (2, 1)

        assert set_row["path"] == f"Lib-{tag} › Set-{tag}"  # noqa: RUF001
        assert (set_row["plate_count"], set_row["subtree_plate_count"]) == (2, 2)
        assert (set_row["on_loan_count"], set_row["overdue_count"]) == (2, 1)

    async def test_closed_loans_do_not_count(self, client: AsyncClient) -> None:
        coll = await _mk_collection(client)
        g = await _mk_group(client, f"G-{uuid.uuid4().hex[:6]}", collection_id=coll["id"])
        plate = await _mk_plate(client, g["id"])
        loan = await _mk_loan(client, plate_ids=[plate["id"]], due_date="2020-01-01")
        item_ids = [i["id"] for i in loan["items"]]
        resp = await client.post(
            f"/api/v1/plate-loans/{loan['id']}/items:cancel", json={"item_ids": item_ids}
        )
        assert resp.status_code == 200, resp.text

        (row,) = (await client.get(f"/api/v1/collections/{coll['id']}/plate-groups")).json()
        assert (row["plate_count"], row["on_loan_count"], row["overdue_count"]) == (1, 0, 0)

    async def test_foreign_org_group_hidden(
        self, client: AsyncClient, editor_client_other_org: AsyncClient
    ) -> None:
        coll = await _mk_collection(client)
        mine = await _mk_group(client, f"Mine-{uuid.uuid4().hex[:6]}", collection_id=coll["id"])
        theirs = await _mk_group(
            client,
            f"Theirs-{uuid.uuid4().hex[:6]}",
            owner_org_id=str(OTHER_ORG_ID),
            collection_id=coll["id"],
        )

        admin_ids = {
            r["group_id"]
            for r in (await client.get(f"/api/v1/collections/{coll['id']}/plate-groups")).json()
        }
        assert admin_ids == {mine["id"], theirs["id"]}

        resp = await editor_client_other_org.get(f"/api/v1/collections/{coll['id']}/plate-groups")
        assert resp.status_code == 200, resp.text
        assert [r["group_id"] for r in resp.json()] == [theirs["id"]]

    async def test_unknown_collection_404(self, client: AsyncClient) -> None:
        resp = await client.get(f"/api/v1/collections/{uuid.uuid4()}/plate-groups")
        assert resp.status_code == 404


class TestCascade:
    async def test_deleting_collection_clears_link(self, client: AsyncClient) -> None:
        coll = await _mk_collection(client)
        g = await _mk_group(client, f"G-{uuid.uuid4().hex[:6]}", collection_id=coll["id"])

        resp = await client.delete(f"/api/v1/collections/{coll['id']}")
        assert resp.status_code == 204, resp.text

        detail = (await client.get(f"/api/v1/plate-groups/{g['id']}")).json()
        assert detail["group"]["collection_id"] is None
        assert detail["group"]["collection_name"] is None
