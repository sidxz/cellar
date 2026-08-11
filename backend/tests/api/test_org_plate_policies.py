"""API tests for org plate policy endpoints (GET/PUT /api/v1/org-plate-policies/{org_id})."""

from __future__ import annotations

import uuid

from httpx import AsyncClient


def _body(**overrides) -> dict:
    body = {
        "require_approval": True,
        "confirmation": "admin_confirm",
        "default_due_days": 14,
        "plates_private": False,
    }
    body.update(overrides)
    return body


class TestGetOrgPlatePolicy:
    async def test_get_unknown_org_returns_defaults(self, client: AsyncClient) -> None:
        org_id = uuid.uuid4()
        resp = await client.get(f"/api/v1/org-plate-policies/{org_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["org_id"] == str(org_id)
        assert data["require_approval"] is True
        assert data["confirmation"] == "admin_confirm"
        assert data["default_due_days"] == 14
        assert data["plates_private"] is False
        assert data["version"] == 1

    async def test_second_get_still_defaults_no_row_created(self, client: AsyncClient) -> None:
        org_id = uuid.uuid4()
        first = await client.get(f"/api/v1/org-plate-policies/{org_id}")
        second = await client.get(f"/api/v1/org-plate-policies/{org_id}")
        assert first.status_code == 200
        assert second.status_code == 200
        assert second.json() == first.json()


class TestSetOrgPlatePolicy:
    async def test_put_as_editor_forbidden(self, editor_client_own_org: AsyncClient) -> None:
        org_id = uuid.uuid4()
        resp = await editor_client_own_org.put(
            f"/api/v1/org-plate-policies/{org_id}", json=_body()
        )
        assert resp.status_code == 403

    async def test_put_as_admin_flips_plates_private(self, client: AsyncClient) -> None:
        org_id = uuid.uuid4()
        resp = await client.put(
            f"/api/v1/org-plate-policies/{org_id}",
            json=_body(plates_private=True),
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["plates_private"] is True
        assert resp.json()["version"] == 1  # first PUT is an INSERT

        got = await client.get(f"/api/v1/org-plate-policies/{org_id}")
        assert got.status_code == 200
        assert got.json()["plates_private"] is True
