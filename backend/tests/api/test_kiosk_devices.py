"""API tests for /api/v1/kiosk-devices."""

from __future__ import annotations

import uuid

from httpx import AsyncClient


async def _mk_device(client: AsyncClient, name: str, **overrides) -> dict:
    body = {"org_id": str(uuid.uuid4()), "name": name, **overrides}
    resp = await client.post("/api/v1/kiosk-devices", json=body)
    assert resp.status_code == 201, resp.text
    return resp.json()


class TestCreate:
    async def test_create_returns_token_once_no_hash_leaked(self, client: AsyncClient) -> None:
        name = f"Kiosk {uuid.uuid4().hex[:8]}"
        device = await _mk_device(client, name)
        assert device["name"] == name
        assert len(device["token"]) > 30
        assert "token_hash" not in device
        assert device["is_active"] is True
        assert device["last_seen_at"] is None

    async def test_duplicate_name_conflicts(self, client: AsyncClient) -> None:
        name = f"Kiosk {uuid.uuid4().hex[:8]}"
        await _mk_device(client, name)
        resp = await client.post(
            "/api/v1/kiosk-devices", json={"org_id": str(uuid.uuid4()), "name": name}
        )
        assert resp.status_code == 409
        assert name in resp.json()["message"]

    async def test_create_for_arbitrary_org_id_succeeds(self, client: AsyncClient) -> None:
        # org_id is not validated against the org directory here — the FE
        # picker constrains input to real orgs, and this admin-only endpoint
        # trusts the caller the same way other org-scoped writes do.
        org_id = uuid.uuid4()
        device = await _mk_device(client, f"Kiosk {uuid.uuid4().hex[:8]}", org_id=str(org_id))
        assert device["org_id"] == str(org_id)

    async def test_editor_forbidden(self, editor_client: AsyncClient) -> None:
        resp = await editor_client.post(
            "/api/v1/kiosk-devices", json={"org_id": str(uuid.uuid4()), "name": "Nope"}
        )
        assert resp.status_code == 403


class TestList:
    async def test_list_shows_device_without_token(self, client: AsyncClient) -> None:
        created = await _mk_device(client, f"Kiosk {uuid.uuid4().hex[:8]}")
        resp = await client.get("/api/v1/kiosk-devices")
        assert resp.status_code == 200, resp.text
        listed = next(d for d in resp.json() if d["id"] == created["id"])
        assert listed["last_seen_at"] is None
        assert "token" not in listed
        assert "token_hash" not in listed

    async def test_viewer_forbidden(self, viewer_client: AsyncClient) -> None:
        resp = await viewer_client.get("/api/v1/kiosk-devices")
        assert resp.status_code == 403


class TestRevoke:
    async def test_revoke_deactivates(self, client: AsyncClient) -> None:
        device = await _mk_device(client, f"Kiosk {uuid.uuid4().hex[:8]}")
        resp = await client.post(f"/api/v1/kiosk-devices/{device['id']}:revoke")
        assert resp.status_code == 200, resp.text
        assert resp.json()["is_active"] is False

    async def test_revoke_twice_is_idempotent(self, client: AsyncClient) -> None:
        device = await _mk_device(client, f"Kiosk {uuid.uuid4().hex[:8]}")
        first = await client.post(f"/api/v1/kiosk-devices/{device['id']}:revoke")
        assert first.status_code == 200, first.text
        second = await client.post(f"/api/v1/kiosk-devices/{device['id']}:revoke")
        assert second.status_code == 200, second.text
        assert second.json()["is_active"] is False
