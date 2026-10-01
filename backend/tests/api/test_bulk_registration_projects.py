"""Bulk registration with a project choice (sync path: TEMPORAL_DISABLED in tests)."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine

from cellar.application.chemical_registration.bulk_registration_orchestrator import (
    BulkRegistrationOrchestrator,
)
from cellar.infrastructure.temporal.orchestrators.bulk_registration import (
    NullBulkRegistrationOrchestrator,
)
from tests.api.conftest import _create_test_app
from tests.fakes.fake_auth import FakeAuth


@pytest.fixture
async def client(
    database_url: str, _run_migrations: None, fake_auth: FakeAuth
) -> AsyncIterator[AsyncClient]:
    """Admin client whose app binds the bulk orchestrator the way app.py does
    without Temporal — so uploads take the in-process (sync) path."""
    app = _create_test_app(
        database_url,
        fake_auth,
        overrides={BulkRegistrationOrchestrator: NullBulkRegistrationOrchestrator()},
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:  # type: ignore[arg-type]
        yield ac
    await app.state.container[AsyncEngine].dispose()


async def _org(client: AsyncClient) -> str:
    resp = await client.post(
        "/api/v1/organizations",
        json={"name": f"BulkRegOrg-{uuid.uuid4().hex[:6]}", "org_type": "internal"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def test_bulk_upload_links_every_row_to_the_projects(client: AsyncClient) -> None:
    org = await _org(client)
    existing = await client.post(
        "/api/v1/molecules",
        json={"name": "AlreadyHere", "smiles": "CCCCCCCCCCCCCCCCCCN", "originating_org_id": org},
    )
    proj = (await client.post("/api/v1/projects", json={"name": "Bulk Reg P"})).json()["id"]
    csv = b"name,smiles\nBulkNew1,CCCCCCCCCCCCCCCCCCCN\nBulkDup,CCCCCCCCCCCCCCCCCCN\n"

    resp = await client.post(
        "/api/v1/bulk-registrations",
        files={"file": ("rows.csv", csv, "text/csv")},
        data={"originating_org_id": org, "file_format": "csv", "project_ids": [proj]},
    )
    assert resp.status_code == 200, resp.text  # sync path (TEMPORAL_DISABLED in API tests)
    items = resp.json()["items"]
    assert all(i["success"] for i in items), items

    stats = await client.get("/api/v1/projects/stats", params={"project_ids": [proj]})
    assert stats.json()[proj]["molecule_count"] == 2  # new row + the deduplicated compound
    linked = await client.get(f"/api/v1/molecules/{existing.json()['molecule']['id']}/projects")
    assert proj in set(linked.json())


async def test_bulk_upload_with_archived_project_starts_nothing(client: AsyncClient) -> None:
    org = await _org(client)
    proj = (await client.post("/api/v1/projects", json={"name": "Archived Bulk P"})).json()["id"]
    assert (await client.post(f"/api/v1/projects/{proj}/archive")).status_code == 200

    resp = await client.post(
        "/api/v1/bulk-registrations",
        files={"file": ("rows.csv", b"name,smiles\nNope,CCCCCCCCCCCCCCCCCCCCN\n", "text/csv")},
        data={"originating_org_id": org, "file_format": "csv", "project_ids": [proj]},
    )
    assert resp.status_code == 422
    listed = await client.get("/api/v1/molecules", params={"q": "Nope"})
    assert listed.json()["items"] == []
