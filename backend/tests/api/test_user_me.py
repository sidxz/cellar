"""API tests for GET /api/v1/user/me."""

from __future__ import annotations

from httpx import AsyncClient

from tests.api.conftest import AUTH_ORG_ID


async def test_me_returns_identity_with_org(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/user/me")
    assert resp.status_code == 200
    body = resp.json()
    assert set(body) == {"user_id", "email", "name", "org_id", "org_slug"}
    assert body["email"] == "test@example.com"
    assert body["name"] == "Test User"
    assert body["org_id"] == str(AUTH_ORG_ID)
