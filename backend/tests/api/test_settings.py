"""API tests for workspace settings endpoints."""

from __future__ import annotations

from httpx import AsyncClient


class TestGetSettings:
    async def test_get_returns_defaults(self, client: AsyncClient) -> None:
        resp = await client.get("/api/v1/settings")
        assert resp.status_code == 200
        data = resp.json()
        assert data["registration_rules"] == {}
        assert data["custom_field_definitions"] == {}
        assert data["default_molecule_type"] is None
        assert data["audit_reason_policy"] == {}
        assert data["signature_required_for"] == []
        assert data["audit_retention_days"] is None
        assert data["formulation_number_scheme"] == {}
        assert data["version"] == 1


class TestUpdateSettings:
    async def test_partial_update(self, client: AsyncClient) -> None:
        # GET first to auto-initialize with defaults (version 1)
        await client.get("/api/v1/settings")
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
        assert data["registration_rules"] == {}  # unchanged
        assert data["version"] == 2

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

    async def test_consecutive_updates_increment_version(self, client: AsyncClient) -> None:
        await client.get("/api/v1/settings")  # initializes with v1
        r1 = await client.patch("/api/v1/settings", json={"audit_retention_days": 90})
        assert r1.json()["version"] == 2
        r2 = await client.patch("/api/v1/settings", json={"audit_retention_days": 180})
        assert r2.json()["version"] == 3
