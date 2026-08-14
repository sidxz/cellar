"""API tests for /api/v1/kiosk — X-Kiosk-Token device auth, no Sentinel session."""

from __future__ import annotations

import uuid

from fastapi import FastAPI
from httpx import AsyncClient

from cellar.infrastructure.sentinel.org_directory import OrgSummary
from cellar.interface.dependencies import get_org_directory
from tests.api.conftest import AUTH_ORG_ID, OTHER_ORG_ID


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


async def _mk_device(client: AsyncClient, org_id: uuid.UUID, name: str) -> dict:
    resp = await client.post("/api/v1/kiosk-devices", json={"org_id": str(org_id), "name": name})
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _mk_loan(client: AsyncClient, **body) -> dict:
    resp = await client.post("/api/v1/plate-loans", json=body)
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _setup_approved_item(
    client: AsyncClient, editor_client_own_org: AsyncClient, barcode: str = "000123"
) -> dict:
    """Admin device for AUTH_ORG_ID + a plate owned by AUTH_ORG_ID, on loan to
    the borrower (also AUTH_ORG_ID here — the org distinction that matters for
    kiosk auth is device.org_id vs plate.owner_org_id, not borrower identity)
    and approved by the admin. Item is APPROVED, ready for a kiosk checkout."""
    device = await _mk_device(client, AUTH_ORG_ID, f"Kiosk {uuid.uuid4().hex[:8]}")
    plate = await _mk_plate(client, barcode)
    loan = await _mk_loan(editor_client_own_org, plate_ids=[plate["id"]])
    approved = await client.post(f"/api/v1/plate-loans/{loan['id']}/items:approve", json={})
    assert approved.status_code == 200, approved.text
    approved_loan = approved.json()
    item = approved_loan["items"][0]
    assert item["status"] == "approved"
    return {
        "token": device["token"],
        "device_id": device["id"],
        "plate": plate,
        "loan_id": approved_loan["id"],
        "item_id": item["id"],
        "due_date": approved_loan["due_date"],
    }


class TestKioskScan:
    async def test_scan_exact_barcode_resolves_checkout(
        self, client: AsyncClient, editor_client_own_org: AsyncClient
    ) -> None:
        setup = await _setup_approved_item(client, editor_client_own_org)
        resp = await client.post(
            "/api/v1/kiosk/scan",
            json={"barcode": "000123"},
            headers={"X-Kiosk-Token": setup["token"]},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["plate_id"] == setup["plate"]["id"]
        assert body["barcode"] == "000123"
        assert body["loan_id"] == setup["loan_id"]
        assert body["item_id"] == setup["item_id"]
        assert body["action"] == "checkout"
        assert body["item_status"] == "approved"
        assert body["due_date"] == setup["due_date"]

    async def test_scan_short_digit_barcode_zfill_chain(
        self, client: AsyncClient, editor_client_own_org: AsyncClient
    ) -> None:
        setup = await _setup_approved_item(client, editor_client_own_org)
        resp = await client.post(
            "/api/v1/kiosk/scan",
            json={"barcode": "123"},
            headers={"X-Kiosk-Token": setup["token"]},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["plate_id"] == setup["plate"]["id"]

    async def test_scan_missing_or_garbage_token_forbidden(
        self, client: AsyncClient, editor_client_own_org: AsyncClient
    ) -> None:
        await _setup_approved_item(client, editor_client_own_org)

        no_token = await client.post("/api/v1/kiosk/scan", json={"barcode": "000123"})
        assert no_token.status_code == 403, no_token.text

        garbage = await client.post(
            "/api/v1/kiosk/scan",
            json={"barcode": "000123"},
            headers={"X-Kiosk-Token": "not-a-real-token"},
        )
        assert garbage.status_code == 403, garbage.text

    async def test_scan_revoked_device_forbidden(
        self, client: AsyncClient, editor_client_own_org: AsyncClient
    ) -> None:
        setup = await _setup_approved_item(client, editor_client_own_org)
        revoke = await client.post(f"/api/v1/kiosk-devices/{setup['device_id']}:revoke")
        assert revoke.status_code == 200, revoke.text

        resp = await client.post(
            "/api/v1/kiosk/scan",
            json={"barcode": "000123"},
            headers={"X-Kiosk-Token": setup["token"]},
        )
        assert resp.status_code == 403, resp.text

    async def test_scan_foreign_org_plate_not_found(
        self, client: AsyncClient, editor_client_own_org: AsyncClient
    ) -> None:
        setup = await _setup_approved_item(client, editor_client_own_org)
        foreign_plate = await _mk_plate(
            client, f"F-{uuid.uuid4().hex[:8]}", owner_org_id=str(OTHER_ORG_ID)
        )
        resp = await client.post(
            "/api/v1/kiosk/scan",
            json={"barcode": foreign_plate["barcode"]},
            headers={"X-Kiosk-Token": setup["token"]},
        )
        assert resp.status_code == 404, resp.text

    async def test_scan_unknown_barcode_not_found(
        self, client: AsyncClient, editor_client_own_org: AsyncClient
    ) -> None:
        setup = await _setup_approved_item(client, editor_client_own_org)
        resp = await client.post(
            "/api/v1/kiosk/scan",
            json={"barcode": f"no-such-plate-{uuid.uuid4().hex[:8]}"},
            headers={"X-Kiosk-Token": setup["token"]},
        )
        assert resp.status_code == 404, resp.text

    async def test_scan_plate_with_no_pending_item_conflicts(
        self, client: AsyncClient, editor_client_own_org: AsyncClient
    ) -> None:
        setup = await _setup_approved_item(client, editor_client_own_org)
        idle_plate = await _mk_plate(client, f"IDLE-{uuid.uuid4().hex[:8]}")
        resp = await client.post(
            "/api/v1/kiosk/scan",
            json={"barcode": idle_plate["barcode"]},
            headers={"X-Kiosk-Token": setup["token"]},
        )
        assert resp.status_code == 409, resp.text
        message = resp.json()["message"]
        # Regression guard: message must render the plain barcode string, not
        # the Barcode VO's raw Pydantic repr (`value='...'`) — see kiosk.py.
        assert idle_plate["barcode"] in message
        assert "value=" not in message


class TestKioskConfirm:
    async def test_confirm_checkout_then_reconfirm_conflicts(
        self, client: AsyncClient, editor_client_own_org: AsyncClient
    ) -> None:
        setup = await _setup_approved_item(client, editor_client_own_org)

        resp = await client.post(
            "/api/v1/kiosk/confirm",
            json={"loan_id": setup["loan_id"], "item_id": setup["item_id"]},
            headers={"X-Kiosk-Token": setup["token"]},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["loan_id"] == setup["loan_id"]
        assert body["item_id"] == setup["item_id"]
        assert body["new_status"] == "checked_out"

        loan_resp = await client.get(f"/api/v1/plate-loans/{setup['loan_id']}")
        assert loan_resp.status_code == 200, loan_resp.text
        item = next(i for i in loan_resp.json()["items"] if i["id"] == setup["item_id"])
        assert item["status"] == "checked_out"

        again = await client.post(
            "/api/v1/kiosk/confirm",
            json={"loan_id": setup["loan_id"], "item_id": setup["item_id"]},
            headers={"X-Kiosk-Token": setup["token"]},
        )
        assert again.status_code == 409, again.text

    async def test_full_return_cycle_closes_loan(
        self, client: AsyncClient, editor_client_own_org: AsyncClient
    ) -> None:
        setup = await _setup_approved_item(client, editor_client_own_org)

        checkout = await client.post(
            "/api/v1/kiosk/confirm",
            json={"loan_id": setup["loan_id"], "item_id": setup["item_id"]},
            headers={"X-Kiosk-Token": setup["token"]},
        )
        assert checkout.status_code == 200, checkout.text

        req_return = await editor_client_own_org.post(
            f"/api/v1/plate-loans/{setup['loan_id']}/items:request-return", json={}
        )
        assert req_return.status_code == 200, req_return.text
        assert req_return.json()["items"][0]["status"] == "return_pending"

        confirm_return = await client.post(
            "/api/v1/kiosk/confirm",
            json={"loan_id": setup["loan_id"], "item_id": setup["item_id"]},
            headers={"X-Kiosk-Token": setup["token"]},
        )
        assert confirm_return.status_code == 200, confirm_return.text
        assert confirm_return.json()["new_status"] == "returned"

        loan_resp = await client.get(f"/api/v1/plate-loans/{setup['loan_id']}")
        assert loan_resp.status_code == 200, loan_resp.text
        assert loan_resp.json()["status"] == "closed"

    async def test_device_last_seen_updates_after_scan(
        self, client: AsyncClient, editor_client_own_org: AsyncClient
    ) -> None:
        setup = await _setup_approved_item(client, editor_client_own_org)
        scan = await client.post(
            "/api/v1/kiosk/scan",
            json={"barcode": "000123"},
            headers={"X-Kiosk-Token": setup["token"]},
        )
        assert scan.status_code == 200, scan.text

        devices = await client.get("/api/v1/kiosk-devices")
        assert devices.status_code == 200, devices.text
        device = next(d for d in devices.json() if d["id"] == setup["device_id"])
        assert device["last_seen_at"] is not None


class TestBorrowerOrgName:
    async def test_borrower_org_name_none_when_directory_lacks_entry(
        self, client: AsyncClient, editor_client_own_org: AsyncClient
    ) -> None:
        setup = await _setup_approved_item(client, editor_client_own_org)
        resp = await client.post(
            "/api/v1/kiosk/scan",
            json={"barcode": "000123"},
            headers={"X-Kiosk-Token": setup["token"]},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["borrower_org_name"] is None

    async def test_borrower_org_name_resolves_with_directory_override(
        self, api_app: FastAPI, client: AsyncClient, editor_client_own_org: AsyncClient
    ) -> None:
        setup = await _setup_approved_item(client, editor_client_own_org)

        class _StubOrgDirectoryWithAuthOrg:
            async def list_orgs(self) -> list[OrgSummary]:
                return [OrgSummary(id=AUTH_ORG_ID, slug="tamu", name="Texas A&M", is_public=True)]

        api_app.dependency_overrides[get_org_directory] = lambda: _StubOrgDirectoryWithAuthOrg()

        resp = await client.post(
            "/api/v1/kiosk/scan",
            json={"barcode": "000123"},
            headers={"X-Kiosk-Token": setup["token"]},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["borrower_org_name"] == "Texas A&M"
