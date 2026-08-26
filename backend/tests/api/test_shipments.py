"""API tests for /api/v1/shipments — polymorphic items, direction, loan link (S17 §6)."""

from __future__ import annotations

import uuid

from httpx import AsyncClient

# ---------------------------------------------------------------------------
# Helpers (also imported by test_shipment_links.py)
# ---------------------------------------------------------------------------


async def _mk_plate(client: AsyncClient, barcode: str | None = None, **overrides) -> dict:
    body = {
        "barcode": barcode or f"PL-{uuid.uuid4().hex[:8]}",
        "plate_label": "Assay plate",
        "format": "96",
        "plate_type": "assay",
        **overrides,
    }
    resp = await client.post("/api/v1/plates", json=body)
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _mk_batch(client: AsyncClient) -> dict:
    """org → molecule → batch (a sample needs a batch which needs a molecule)."""
    org = await client.post(
        "/api/v1/organizations",
        json={"name": f"Org-{uuid.uuid4().hex[:6]}", "org_type": "internal"},
    )
    assert org.status_code == 201, org.text
    mol = await client.post(
        "/api/v1/molecules",
        json={
            "smiles": "CCO",
            "name": f"mol-{uuid.uuid4().hex[:6]}",
            "originating_org_id": org.json()["id"],
        },
    )
    assert mol.status_code in (200, 201), mol.text
    batch = await client.post(
        "/api/v1/batches",
        json={
            "molecule_id": mol.json()["molecule"]["id"],
            "source": "synthesized",
            "amount_value": 100.0,
            "amount_unit": "mg",
        },
    )
    assert batch.status_code in (200, 201), batch.text
    return batch.json()["batch"]


async def _mk_sample(client: AsyncClient, batch_id: str, barcode: str | None = None) -> dict:
    resp = await client.post(
        "/api/v1/samples",
        json={
            "batch_id": batch_id,
            "barcode": barcode or f"VIAL-{uuid.uuid4().hex[:8]}",
            "container_type": "vial",
            "amount_value": 20.0,
            "amount_unit": "mg",
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _sample_item(sample: dict, value: float | None = 5.0, unit: str | None = "mg") -> dict:
    return {
        "item_type": "sample",
        "item_id": sample["id"],
        "amount_value": value,
        "amount_unit": unit,
    }


def _plate_item(plate: dict, **extra) -> dict:
    return {"item_type": "plate", "item_id": plate["id"], **extra}


async def _post_shipment(client: AsyncClient, *items: dict, **body):
    return await client.post(
        "/api/v1/shipments",
        json={"destination_org_id": str(uuid.uuid4()), "items": list(items), **body},
    )


async def _mk_shipment(client: AsyncClient, *items: dict, **body) -> dict:
    resp = await _post_shipment(client, *items, **body)
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _mk_loan(client: AsyncClient, plate: dict) -> dict:
    resp = await client.post("/api/v1/plate-loans", json={"plate_ids": [plate["id"]]})
    assert resp.status_code == 201, resp.text
    return resp.json()


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------


class TestCreateShipment:
    async def test_sample_item_is_enriched(self, client: AsyncClient) -> None:
        batch = await _mk_batch(client)
        sample = await _mk_sample(client, batch["id"])

        s = await _mk_shipment(client, _sample_item(sample))

        assert s["status"] == "preparing"
        assert s["direction"] == "outbound"
        assert s["loan_id"] is None
        [item] = s["items"]
        assert item["item_type"] == "sample"
        assert item["item_id"] == sample["id"]
        assert item["barcode"] == sample["barcode"]
        assert item["label"] == batch["batch_number"]
        assert item["amount_value"] == 5.0
        assert item["amount_unit"] == "mg"

    async def test_plate_item_ships_whole(self, client: AsyncClient) -> None:
        plate = await _mk_plate(client)

        s = await _mk_shipment(client, _plate_item(plate))

        [item] = s["items"]
        assert item["item_type"] == "plate"
        assert item["item_id"] == plate["id"]
        assert item["barcode"] == plate["barcode"]
        assert item["label"] == plate["plate_label"]
        assert item["amount_value"] is None
        assert item["amount_unit"] is None

    async def test_mixed_shipment(self, client: AsyncClient) -> None:
        plate = await _mk_plate(client)
        batch = await _mk_batch(client)
        sample = await _mk_sample(client, batch["id"])

        s = await _mk_shipment(client, _plate_item(plate), _sample_item(sample, 2.5, "mL"))

        assert [i["item_type"] for i in s["items"]] == ["plate", "sample"]
        assert s["items"][1]["amount_unit"] == "mL"

    async def test_sample_without_amount_is_422(self, client: AsyncClient) -> None:
        batch = await _mk_batch(client)
        sample = await _mk_sample(client, batch["id"])

        resp = await _post_shipment(client, _sample_item(sample, None, None))

        assert resp.status_code == 422, resp.text

    async def test_plate_with_amount_is_422(self, client: AsyncClient) -> None:
        plate = await _mk_plate(client)

        resp = await _post_shipment(client, _plate_item(plate, amount_value=1.0, amount_unit="mg"))

        assert resp.status_code == 422, resp.text

    async def test_unknown_item_type_is_422(self, client: AsyncClient) -> None:
        resp = await _post_shipment(client, {"item_type": "vial", "item_id": str(uuid.uuid4())})

        assert resp.status_code == 422, resp.text

    async def test_unknown_sample_is_404(self, client: AsyncClient) -> None:
        resp = await _post_shipment(client, _sample_item({"id": str(uuid.uuid4())}))

        assert resp.status_code == 404, resp.text

    async def test_hidden_plate_is_404(
        self, editor_client_own_org: AsyncClient, editor_client_other_org: AsyncClient
    ) -> None:
        theirs = await _mk_plate(editor_client_other_org)  # owner = OTHER_ORG

        resp = await _post_shipment(editor_client_own_org, _plate_item(theirs))
        assert resp.status_code == 404, resp.text  # hidden == missing

        resp = await _post_shipment(editor_client_other_org, _plate_item(theirs))
        assert resp.status_code == 201, resp.text

    async def test_inbound_with_loan_link(self, client: AsyncClient) -> None:
        plate = await _mk_plate(client)
        loan = await _mk_loan(client, plate)

        s = await _mk_shipment(client, _plate_item(plate), direction="inbound", loan_id=loan["id"])

        assert s["direction"] == "inbound"
        assert s["loan_id"] == loan["id"]

    async def test_unknown_loan_is_404(self, client: AsyncClient) -> None:
        plate = await _mk_plate(client)

        resp = await _post_shipment(client, _plate_item(plate), loan_id=str(uuid.uuid4()))

        assert resp.status_code == 404, resp.text

    async def test_hidden_loan_is_404(
        self, editor_client_own_org: AsyncClient, editor_client_other_org: AsyncClient
    ) -> None:
        theirs = await _mk_plate(editor_client_other_org)
        their_loan = await _mk_loan(editor_client_other_org, theirs)  # owner = borrower = OTHER
        mine = await _mk_plate(editor_client_own_org)

        resp = await _post_shipment(
            editor_client_own_org, _plate_item(mine), loan_id=their_loan["id"]
        )

        assert resp.status_code == 404, resp.text

    async def test_viewer_cannot_create(self, viewer_client: AsyncClient) -> None:
        resp = await _post_shipment(viewer_client, _plate_item({"id": str(uuid.uuid4())}))

        assert resp.status_code == 403, resp.text


# ---------------------------------------------------------------------------
# Read
# ---------------------------------------------------------------------------


class TestReadShipments:
    async def test_list_summary_has_direction_and_item_count(self, client: AsyncClient) -> None:
        plate = await _mk_plate(client)
        batch = await _mk_batch(client)
        sample = await _mk_sample(client, batch["id"])
        s = await _mk_shipment(
            client, _plate_item(plate), _sample_item(sample), direction="inbound"
        )

        listed = await client.get("/api/v1/shipments")
        assert listed.status_code == 200, listed.text
        row = next(r for r in listed.json() if r["id"] == s["id"])

        assert row["direction"] == "inbound"
        assert row["item_count"] == 2
        assert row["loan_id"] is None
        assert "items" not in row

    async def test_get_returns_enriched_items(self, client: AsyncClient) -> None:
        plate = await _mk_plate(client)
        s = await _mk_shipment(client, _plate_item(plate))

        got = await client.get(f"/api/v1/shipments/{s['id']}")

        assert got.status_code == 200, got.text
        assert got.json()["items"][0]["barcode"] == plate["barcode"]
        assert got.json()["items"][0]["label"] == plate["plate_label"]

    async def test_get_missing_is_404(self, client: AsyncClient) -> None:
        got = await client.get(f"/api/v1/shipments/{uuid.uuid4()}")

        assert got.status_code == 404


# ---------------------------------------------------------------------------
# Lifecycle + item management
# ---------------------------------------------------------------------------


class TestLifecycle:
    async def test_ship_in_transit_deliver(self, client: AsyncClient) -> None:
        plate = await _mk_plate(client)
        s = await _mk_shipment(client, _plate_item(plate))
        url = f"/api/v1/shipments/{s['id']}"

        shipped = await client.post(f"{url}/ship", json={"tracking_number": "FX-1"})
        assert shipped.status_code == 200, shipped.text
        assert shipped.json()["status"] == "shipped"
        assert shipped.json()["tracking_number"] == "FX-1"
        assert shipped.json()["shipping_date"] is not None

        transit = await client.post(f"{url}/in-transit")
        assert transit.json()["status"] == "in_transit"

        delivered = await client.post(f"{url}/deliver", json={"received_date": "2026-09-01"})
        assert delivered.status_code == 200, delivered.text
        assert delivered.json()["status"] == "delivered"
        assert delivered.json()["received_date"] == "2026-09-01"
        assert delivered.json()["items"][0]["barcode"] == plate["barcode"]

    async def test_add_plate_item_to_preparing(self, client: AsyncClient) -> None:
        batch = await _mk_batch(client)
        sample = await _mk_sample(client, batch["id"])
        plate = await _mk_plate(client)
        s = await _mk_shipment(client, _sample_item(sample))

        resp = await client.post(f"/api/v1/shipments/{s['id']}/items", json=_plate_item(plate))

        assert resp.status_code == 201, resp.text
        assert [i["item_type"] for i in resp.json()["items"]] == ["sample", "plate"]
        assert resp.json()["items"][1]["label"] == plate["plate_label"]

    async def test_add_hidden_plate_is_404(
        self, editor_client_own_org: AsyncClient, editor_client_other_org: AsyncClient
    ) -> None:
        mine = await _mk_plate(editor_client_own_org)
        theirs = await _mk_plate(editor_client_other_org)
        s = await _mk_shipment(editor_client_own_org, _plate_item(mine))

        resp = await editor_client_own_org.post(
            f"/api/v1/shipments/{s['id']}/items", json=_plate_item(theirs)
        )

        assert resp.status_code == 404, resp.text

    async def test_patch_loan_set_and_clear(self, client: AsyncClient) -> None:
        plate = await _mk_plate(client)
        loan = await _mk_loan(client, plate)
        s = await _mk_shipment(client, _plate_item(plate))
        url = f"/api/v1/shipments/{s['id']}"

        set_ = await client.patch(url, json={"loan_id": loan["id"]})
        assert set_.status_code == 200, set_.text
        assert set_.json()["loan_id"] == loan["id"]

        other = await client.patch(url, json={"carrier": "UPS"})
        assert other.json()["loan_id"] == loan["id"]  # omitted field leaves it alone
        assert other.json()["carrier"] == "UPS"

        cleared = await client.patch(url, json={"loan_id": None})
        assert cleared.json()["loan_id"] is None

    async def test_patch_unknown_loan_is_404(self, client: AsyncClient) -> None:
        plate = await _mk_plate(client)
        s = await _mk_shipment(client, _plate_item(plate))

        resp = await client.patch(
            f"/api/v1/shipments/{s['id']}", json={"loan_id": str(uuid.uuid4())}
        )

        assert resp.status_code == 404, resp.text
