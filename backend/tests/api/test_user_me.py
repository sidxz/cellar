"""API tests for GET /api/v1/user/me."""

from __future__ import annotations

from httpx import AsyncClient

from tests.api.conftest import AUTH_ORG_ID


async def test_me_returns_identity_with_org(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/user/me")
    assert resp.status_code == 200
    body = resp.json()
    assert set(body) == {
        "user_id",
        "email",
        "name",
        "org_id",
        "org_slug",
        "workspace_role",
        "is_admin",
    }
    assert body["email"] == "test@example.com"
    assert body["name"] == "Test User"
    assert body["org_id"] == str(AUTH_ORG_ID)
    assert body["is_admin"] is True
    assert body["workspace_role"] == "admin"


async def test_me_reports_non_admin_editor_role(editor_client: AsyncClient) -> None:
    resp = await editor_client.get("/api/v1/user/me")
    assert resp.status_code == 200
    body = resp.json()
    assert body["is_admin"] is False
    assert body["workspace_role"] == "editor"
