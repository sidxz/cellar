"""API tests for org plate policy endpoints (GET/PUT /api/v1/org-plate-policies/{org_id})."""

from __future__ import annotations

import uuid

import sqlalchemy as sa
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine


async def _policy_row_count(api_app: FastAPI, org_id: uuid.UUID) -> int:
    engine: AsyncEngine = api_app.state.container[AsyncEngine]
    async with engine.connect() as conn:
        result = await conn.execute(
            sa.text("SELECT count(*) FROM org_plate_policies WHERE org_id = :org_id"),
            {"org_id": org_id},
        )
        return result.scalar_one()


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

    async def test_second_get_still_defaults_no_row_created(
        self, client: AsyncClient, api_app: FastAPI
    ) -> None:
        org_id = uuid.uuid4()
        first = await client.get(f"/api/v1/org-plate-policies/{org_id}")
        second = await client.get(f"/api/v1/org-plate-policies/{org_id}")
        assert first.status_code == 200
        assert second.status_code == 200
        assert second.json() == first.json()
        # Response equality alone can't catch a silently-persisted default row
        # (it would serialize identically) — prove absence at the DB level.
        assert await _policy_row_count(api_app, org_id) == 0


class TestSetOrgPlatePolicy:
    async def test_put_as_editor_forbidden(self, editor_client_own_org: AsyncClient) -> None:
        org_id = uuid.uuid4()
        resp = await editor_client_own_org.put(
            f"/api/v1/org-plate-policies/{org_id}", json=_body()
        )
        assert resp.status_code == 403

    async def test_put_as_admin_flips_plates_private(
        self, client: AsyncClient, api_app: FastAPI
    ) -> None:
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
        # Sanity for the no-hidden-write test's counter: a real PUT DOES create a row.
        assert await _policy_row_count(api_app, org_id) == 1
