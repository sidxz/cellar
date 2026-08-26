"""API tests for the shipment links — resolve-items + the plate / sample / loan reads (S17 §6)."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine

from tests.api.conftest import _create_test_app
from tests.api.test_shipments import (
    _mk_batch,
    _mk_loan,
    _mk_plate,
    _mk_sample,
    _mk_shipment,
    _plate_item,
    _sample_item,
)
from tests.fakes.fake_auth import FakeAuth


@asynccontextmanager
async def _client_as(
    database_url: str, workspace_id: uuid.UUID, **auth_kwargs
) -> AsyncIterator[AsyncClient]:
    """An ad-hoc editor client for a genuinely unrelated org (fresh uuid4 org_id)."""
    auth_kwargs.setdefault("role", "editor")
    auth = FakeAuth(workspace_id=workspace_id, **auth_kwargs)
    app = _create_test_app(database_url, auth)
    transport = ASGITransport(app=app)  # type: ignore[arg-type]
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    await app.state.container[AsyncEngine].dispose()


# ---------------------------------------------------------------------------
# POST /shipments/resolve-items
# ---------------------------------------------------------------------------


class TestResolveItems:
    async def test_plate_padded_sample_and_unknown(self, client: AsyncClient) -> None:
        plate = await _mk_plate(client, "005261")
        batch = await _mk_batch(client)
        sample = await _mk_sample(client, batch["id"], barcode="VIAL-77")

        resp = await client.post(
            "/api/v1/shipments/resolve-items",
            json={"barcodes": ["5261", "VIAL-77", "", "nope"]},
        )

        assert resp.status_code == 200, resp.text
        assert resp.json() == [
            {
                "barcode": "5261",
                "item_type": "plate",
                "item_id": plate["id"],
                "label": plate["plate_label"],
                "error": None,
            },
            {
                "barcode": "VIAL-77",
                "item_type": "sample",
                "item_id": sample["id"],
                "label": batch["batch_number"],
                "error": None,
            },
            {
                "barcode": "nope",
                "item_type": None,
                "item_id": None,
                "label": None,
                "error": "Unknown barcode 'nope'",
            },
        ]

    async def test_hidden_plate_reads_as_unknown(
        self, editor_client_own_org: AsyncClient, editor_client_other_org: AsyncClient
    ) -> None:
        theirs = await _mk_plate(editor_client_other_org)
        body = {"barcodes": [theirs["barcode"]]}

        hidden = await editor_client_own_org.post("/api/v1/shipments/resolve-items", json=body)
        assert hidden.status_code == 200, hidden.text
        [row] = hidden.json()
        assert row["item_type"] is None
        assert row["error"] == f"Unknown barcode '{theirs['barcode']}'"  # same wording as unknown

        own = await editor_client_other_org.post("/api/v1/shipments/resolve-items", json=body)
        assert own.json()[0]["item_id"] == theirs["id"]

    async def test_viewer_is_403(self, viewer_client: AsyncClient) -> None:
        resp = await viewer_client.post(
            "/api/v1/shipments/resolve-items", json={"barcodes": ["x"]}
        )

        assert resp.status_code == 403, resp.text


# ---------------------------------------------------------------------------
# GET /plates/{id}/shipments
# ---------------------------------------------------------------------------


class TestPlateShipments:
    async def test_rows_newest_first(self, client: AsyncClient) -> None:
        plate = await _mk_plate(client)
        first = await _mk_shipment(client, _plate_item(plate), carrier="FedEx")
        second = await _mk_shipment(client, _plate_item(plate), direction="inbound")

        resp = await client.get(f"/api/v1/plates/{plate['id']}/shipments")

        assert resp.status_code == 200, resp.text
        rows = resp.json()
        assert [r["shipment_id"] for r in rows] == [second["id"], first["id"]]
        assert rows[0]["direction"] == "inbound"
        assert rows[0]["status"] == "preparing"
        assert rows[0]["amount_value"] is None
        assert rows[1]["carrier"] == "FedEx"
        assert set(rows[0]) == {
            "shipment_id",
            "direction",
            "status",
            "destination_org_id",
            "tracking_number",
            "carrier",
            "shipping_date",
            "received_date",
            "amount_value",
            "amount_unit",
            "created_at",
        }

    async def test_never_shipped_is_empty(self, client: AsyncClient) -> None:
        plate = await _mk_plate(client)

        resp = await client.get(f"/api/v1/plates/{plate['id']}/shipments")

        assert resp.status_code == 200
        assert resp.json() == []

    async def test_hidden_plate_is_404(
        self, editor_client_own_org: AsyncClient, editor_client_other_org: AsyncClient
    ) -> None:
        theirs = await _mk_plate(editor_client_other_org)
        await _mk_shipment(editor_client_other_org, _plate_item(theirs))

        hidden = await editor_client_own_org.get(f"/api/v1/plates/{theirs['id']}/shipments")
        assert hidden.status_code == 404, hidden.text

        own = await editor_client_other_org.get(f"/api/v1/plates/{theirs['id']}/shipments")
        assert own.status_code == 200
        assert len(own.json()) == 1

    async def test_missing_plate_is_404(self, client: AsyncClient) -> None:
        resp = await client.get(f"/api/v1/plates/{uuid.uuid4()}/shipments")

        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# GET /samples/{id}/shipments
# ---------------------------------------------------------------------------


class TestSampleShipments:
    async def test_rows_carry_amount(self, client: AsyncClient) -> None:
        batch = await _mk_batch(client)
        sample = await _mk_sample(client, batch["id"])
        s = await _mk_shipment(client, _sample_item(sample, 5.0, "mg"))

        resp = await client.get(f"/api/v1/samples/{sample['id']}/shipments")

        assert resp.status_code == 200, resp.text
        [row] = resp.json()
        assert row["shipment_id"] == s["id"]
        assert row["amount_value"] == 5.0
        assert row["amount_unit"] == "mg"

    async def test_missing_sample_is_404(self, client: AsyncClient) -> None:
        resp = await client.get(f"/api/v1/samples/{uuid.uuid4()}/shipments")

        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# GET /plate-loans/{id}/shipments
# ---------------------------------------------------------------------------


class TestLoanShipments:
    async def test_rows_for_loan(self, client: AsyncClient) -> None:
        plate = await _mk_plate(client)
        loan = await _mk_loan(client, plate)
        await _mk_shipment(client, _plate_item(plate))  # not linked
        linked = await _mk_shipment(client, _plate_item(plate), loan_id=loan["id"])

        resp = await client.get(f"/api/v1/plate-loans/{loan['id']}/shipments")

        assert resp.status_code == 200, resp.text
        [row] = resp.json()
        assert row["shipment_id"] == linked["id"]
        assert row["amount_value"] is None

    async def test_loan_visibility(
        self,
        editor_client_other_org: AsyncClient,
        database_url: str,
        workspace_id: uuid.UUID,
    ) -> None:
        plate = await _mk_plate(editor_client_other_org)
        loan = await _mk_loan(editor_client_other_org, plate)  # owner = borrower = OTHER_ORG

        async with _client_as(database_url, workspace_id, org_id=uuid.uuid4()) as unrelated:
            resp = await unrelated.get(f"/api/v1/plate-loans/{loan['id']}/shipments")
            assert resp.status_code == 404, resp.text

        own = await editor_client_other_org.get(f"/api/v1/plate-loans/{loan['id']}/shipments")
        assert own.status_code == 200, own.text

    async def test_missing_loan_is_404(self, client: AsyncClient) -> None:
        resp = await client.get(f"/api/v1/plate-loans/{uuid.uuid4()}/shipments")

        assert resp.status_code == 404
