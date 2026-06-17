"""API tests for the build-identity endpoint."""

from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_version_endpoint_returns_build_identity(client: AsyncClient) -> None:
    resp = await client.get("/version")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["name"] == "cellar-backend"
    assert set(body) == {"name", "version", "git_sha", "build_date", "environment"}
    assert isinstance(body["version"], str) and body["version"]


@pytest.mark.asyncio
async def test_version_reports_injected_build_env(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CELLAR_VERSION", "1.4.0")
    monkeypatch.setenv("CELLAR_GIT_SHA", "84e7848")
    monkeypatch.setenv("APP_ENV", "production")
    resp = await client.get("/version")
    body = resp.json()
    assert body["version"] == "1.4.0"
    assert body["git_sha"] == "84e7848"
    assert body["environment"] == "production"
