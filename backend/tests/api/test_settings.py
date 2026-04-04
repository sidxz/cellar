"""API tests for workspace settings endpoints."""

from __future__ import annotations

from httpx import AsyncClient


class TestGetSettings:
    async def test_get_returns_defaults_without_persisting(self, client: AsyncClient) -> None:
        resp = await client.get("/api/v1/settings")
        assert resp.status_code == 200
        data = resp.json()
        assert data["registration_rules"] == {}
        assert data["default_molecule_type"] is None
        assert data["signature_required_for"] == []
        assert data["audit_retention_days"] is None
        assert data["version"] == 1


class TestUpdateSettings:
    async def test_first_patch_creates_settings(self, client: AsyncClient) -> None:
        # First PATCH creates settings (INSERT) — version 1
        resp = await client.patch(
            "/api/v1/settings",
            json={
                "default_molecule_type": "small_molecule",
                "audit_retention_days": 365,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["default_molecule_type"] == "small_molecule"
        assert data["audit_retention_days"] == 365
        assert data["registration_rules"] == {}  # default
        assert data["version"] == 1  # INSERT, not UPDATE

    async def test_second_patch_increments_version(self, client: AsyncClient) -> None:
        # First PATCH creates (v1)
        await client.patch("/api/v1/settings", json={"audit_retention_days": 90})
        # Second PATCH updates (v2)
        resp = await client.patch("/api/v1/settings", json={"audit_retention_days": 180})
        assert resp.status_code == 200
        assert resp.json()["audit_retention_days"] == 180
        assert resp.json()["version"] == 2

    async def test_update_signature_required(self, client: AsyncClient) -> None:
        resp = await client.patch(
            "/api/v1/settings",
            json={"signature_required_for": ["registration", "disclosure"]},
        )
        assert resp.status_code == 200
        assert resp.json()["signature_required_for"] == ["registration", "disclosure"]

    async def test_update_registration_rules(self, client: AsyncClient) -> None:
        rules = {"numbering": "CV-{seq}", "salt_stripping": True}
        resp = await client.patch(
            "/api/v1/settings",
            json={"registration_rules": rules},
        )
        assert resp.status_code == 200
        assert resp.json()["registration_rules"] == rules

    async def test_get_after_patch_returns_persisted(self, client: AsyncClient) -> None:
        await client.patch("/api/v1/settings", json={"default_molecule_type": "biologic"})
        resp = await client.get("/api/v1/settings")
        assert resp.status_code == 200
        assert resp.json()["default_molecule_type"] == "biologic"
