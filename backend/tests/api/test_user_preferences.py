"""API tests for user preferences endpoints."""

from __future__ import annotations

from httpx import AsyncClient


class TestGetPreferences:
    async def test_get_returns_defaults(self, client: AsyncClient) -> None:
        resp = await client.get("/api/v1/user/preferences")
        assert resp.status_code == 200
        data = resp.json()
        assert data["theme"] == "dark"
        assert data["sidebar_collapsed"] is False


class TestUpdatePreferences:
    async def test_update_theme(self, client: AsyncClient) -> None:
        resp = await client.patch(
            "/api/v1/user/preferences",
            json={"theme": "light"},
        )
        assert resp.status_code == 200
        assert resp.json()["theme"] == "light"

    async def test_update_sidebar(self, client: AsyncClient) -> None:
        resp = await client.patch(
            "/api/v1/user/preferences",
            json={"sidebar_collapsed": True},
        )
        assert resp.status_code == 200
        assert resp.json()["sidebar_collapsed"] is True

    async def test_partial_update_preserves_other_fields(self, client: AsyncClient) -> None:
        # Set theme to light
        await client.patch("/api/v1/user/preferences", json={"theme": "light"})
        # Update only sidebar
        resp = await client.patch(
            "/api/v1/user/preferences",
            json={"sidebar_collapsed": True},
        )
        assert resp.status_code == 200
        assert resp.json()["theme"] == "light"  # preserved
        assert resp.json()["sidebar_collapsed"] is True

    async def test_roundtrip(self, client: AsyncClient) -> None:
        await client.patch(
            "/api/v1/user/preferences",
            json={"theme": "system", "sidebar_collapsed": True},
        )
        resp = await client.get("/api/v1/user/preferences")
        assert resp.status_code == 200
        assert resp.json()["theme"] == "system"
        assert resp.json()["sidebar_collapsed"] is True
