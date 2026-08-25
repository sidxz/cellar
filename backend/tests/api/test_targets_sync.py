"""POST /api/v1/targets/sync + best-effort refresh on GET /api/v1/targets.

The prot-cellar adapter is replaced with an in-memory ``TargetSource`` via the
container ``overrides`` seam — no network in tests.
"""

from __future__ import annotations

import dataclasses
import uuid
from collections.abc import AsyncIterator, Mapping

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine

from cellar.application.screening.target_source import SourceTarget, TargetSource
from cellar.domain.shared.errors import AuthorizationError, ServiceUnavailableError
from tests.api.conftest import AUTH_ORG_ID, _create_test_app
from tests.fakes.fake_auth import FakeAuth

pytestmark = pytest.mark.asyncio

FWD = {"Authorization": "Bearer idp-token", "X-Authz-Token": "authz-token"}


class StubSource:
    def __init__(self) -> None:
        self.targets: list[SourceTarget] = []
        self.error: Exception | None = None
        self.calls: list[Mapping[str, str]] = []

    async def fetch_all(self, *, forwarded_headers: Mapping[str, str]) -> list[SourceTarget]:
        self.calls.append(dict(forwarded_headers))
        if self.error:
            raise self.error
        return list(self.targets)


@pytest.fixture
def stub_source() -> StubSource:
    return StubSource()


async def _app_for(database_url: str, role: str, workspace_id: uuid.UUID, stub: StubSource):
    auth = FakeAuth(role=role, workspace_id=workspace_id, org_id=AUTH_ORG_ID)
    return _create_test_app(database_url, auth, overrides={TargetSource: stub})


@pytest.fixture
async def admin_sync_client(
    database_url: str, _run_migrations: None, workspace_id: uuid.UUID, stub_source: StubSource
) -> AsyncIterator[AsyncClient]:
    app = await _app_for(database_url, "admin", workspace_id, stub_source)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
    await app.state.container[AsyncEngine].dispose()


@pytest.fixture
async def viewer_sync_client(
    database_url: str, _run_migrations: None, workspace_id: uuid.UUID, stub_source: StubSource
) -> AsyncIterator[AsyncClient]:
    app = await _app_for(database_url, "viewer", workspace_id, stub_source)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
    await app.state.container[AsyncEngine].dispose()


def _src(name: str, version: int = 1) -> SourceTarget:
    return SourceTarget(uuid.uuid4(), name, "single_protein", "Mtb", None, version)


async def test_admin_sync_upserts_mirror_and_forwards_only_auth_headers(
    admin_sync_client: AsyncClient, stub_source: StubSource
) -> None:
    stub_source.targets = [_src("NadD"), _src("AspS")]

    resp = await admin_sync_client.post(
        "/api/v1/targets/sync", headers={**FWD, "X-Service-Key": "must-not-forward"}
    )
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"fetched": 2, "created": 2, "updated": 0, "skipped": 0}
    assert stub_source.calls == [
        {"authorization": "Bearer idp-token", "x-authz-token": "authz-token"}
    ]

    listed = await admin_sync_client.get("/api/v1/targets")
    names = sorted(t["name"] for t in listed.json()["items"])
    assert names == ["AspS", "NadD"]
    assert {t["id"] for t in listed.json()["items"]} == {str(t.id) for t in stub_source.targets}

    # Second forced sync: nothing changed → all skipped.
    again = await admin_sync_client.post("/api/v1/targets/sync", headers=FWD)
    assert again.json() == {"fetched": 2, "created": 0, "updated": 0, "skipped": 2}

    # A source-side name/chembl_id/version change is a real update, not a
    # re-create — proves _update_model persists source_version + chembl_id.
    nadd = next(t for t in stub_source.targets if t.name == "NadD")
    stub_source.targets = [
        dataclasses.replace(nadd, name="NAD Kinase", chembl_id="CHEMBL9", version=2),
        next(t for t in stub_source.targets if t.name == "AspS"),
    ]
    changed = await admin_sync_client.post("/api/v1/targets/sync", headers=FWD)
    assert changed.json() == {"fetched": 2, "created": 0, "updated": 1, "skipped": 1}

    relisted = await admin_sync_client.get("/api/v1/targets")
    updated_row = next(t for t in relisted.json()["items"] if t["id"] == str(nadd.id))
    assert updated_row["name"] == "NAD Kinase"
    assert updated_row["chembl_id"] == "CHEMBL9"


async def test_sync_requires_admin(viewer_sync_client: AsyncClient) -> None:
    resp = await viewer_sync_client.post("/api/v1/targets/sync", headers=FWD)
    assert resp.status_code == 403


async def test_sync_surfaces_prot_cellar_auth_and_outage(
    admin_sync_client: AsyncClient, stub_source: StubSource
) -> None:
    stub_source.error = AuthorizationError(
        "prot-cellar refused the request: editor role required",
        detail="(403) editor required. Target reads in prot-cellar require the editor role.",
    )
    resp = await admin_sync_client.post("/api/v1/targets/sync", headers=FWD)
    assert resp.status_code == 403
    assert "editor" in resp.json()["message"]
    assert "editor" in resp.json()["detail"]

    stub_source.error = ServiceUnavailableError(
        "prot-cellar unreachable", detail="connection refused"
    )
    resp = await admin_sync_client.post("/api/v1/targets/sync", headers=FWD)
    assert resp.status_code == 503
    assert "connection refused" in resp.json()["detail"]


async def test_list_serves_mirror_when_source_raises_unexpected_error(
    admin_sync_client: AsyncClient,
    viewer_sync_client: AsyncClient,
    stub_source: StubSource,
    make_target,
) -> None:
    """A non-DomainError bug in the adapter (e.g. a malformed payload raising
    KeyError) must not 500 the read path — and must still 503 the admin sync."""
    seeded = await make_target("Seeded")
    stub_source.error = KeyError("items")

    resp = await viewer_sync_client.get("/api/v1/targets", headers=FWD)
    assert resp.status_code == 200
    assert [t["id"] for t in resp.json()["items"]] == [seeded]

    sync_resp = await admin_sync_client.post("/api/v1/targets/sync", headers=FWD)
    assert sync_resp.status_code == 503


async def test_list_refreshes_best_effort_and_serves_mirror_when_source_fails(
    viewer_sync_client: AsyncClient, stub_source: StubSource, make_target
) -> None:
    seeded = await make_target("Seeded")
    stub_source.error = ServiceUnavailableError("down")

    resp = await viewer_sync_client.get("/api/v1/targets", headers=FWD)
    assert resp.status_code == 200
    assert [t["id"] for t in resp.json()["items"]] == [seeded]
    assert len(stub_source.calls) == 1

    # Fresh (attempt marked) → no second call within the TTL.
    await viewer_sync_client.get("/api/v1/targets", headers=FWD)
    assert len(stub_source.calls) == 1


async def test_list_without_forwardable_auth_skips_refresh(
    admin_sync_client: AsyncClient, stub_source: StubSource
) -> None:
    resp = await admin_sync_client.get("/api/v1/targets")  # FakeAuth path: no Duar headers
    assert resp.status_code == 200
    assert stub_source.calls == []


async def test_local_mutation_routes_are_gone(admin_sync_client: AsyncClient) -> None:
    create = await admin_sync_client.post(
        "/api/v1/targets", json={"name": "x", "target_type": "single_protein"}
    )
    assert create.status_code == 405
    tid = uuid.uuid4()
    patch = await admin_sync_client.patch(f"/api/v1/targets/{tid}", json={"name": "x"})
    assert patch.status_code == 405
    delete = await admin_sync_client.delete(f"/api/v1/targets/{tid}")
    assert delete.status_code == 405
