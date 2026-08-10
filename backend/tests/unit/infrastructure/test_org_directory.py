"""OrgDirectory — Sentinel internal org list with a per-process TTL cache."""

import time
import uuid

import httpx
import pytest

from cellar.infrastructure.sentinel.org_directory import OrgDirectory, OrgSummary

ORGS = [
    {"id": str(uuid.uuid4()), "slug": "abbvie", "name": "AbbVie", "is_public": False, "enabled": True},
    {"id": str(uuid.uuid4()), "slug": "public", "name": "Public", "is_public": True, "enabled": True},
]


def _transport(calls: list) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        assert request.headers["X-Service-Key"] == "svc-key"
        assert request.url.path == "/organizations"
        return httpx.Response(200, json=ORGS)

    return httpx.MockTransport(handler)


@pytest.mark.asyncio
async def test_lists_and_maps_orgs():
    calls: list = []
    directory = OrgDirectory("http://sentinel", "svc-key", transport=_transport(calls))
    orgs = await directory.list_orgs()
    assert orgs == [
        OrgSummary(id=uuid.UUID(ORGS[0]["id"]), slug="abbvie", name="AbbVie", is_public=False),
        OrgSummary(id=uuid.UUID(ORGS[1]["id"]), slug="public", name="Public", is_public=True),
    ]


@pytest.mark.asyncio
async def test_caches_within_ttl():
    calls: list = []
    directory = OrgDirectory("http://sentinel", "svc-key", ttl_seconds=300, transport=_transport(calls))
    await directory.list_orgs()
    await directory.list_orgs()
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_refetches_after_ttl(monkeypatch):
    calls: list = []
    directory = OrgDirectory("http://sentinel", "svc-key", ttl_seconds=300, transport=_transport(calls))
    await directory.list_orgs()
    baseline = time.monotonic()
    monkeypatch.setattr(
        "cellar.infrastructure.sentinel.org_directory.time.monotonic",
        lambda: baseline + 400.0,
    )
    await directory.list_orgs()
    assert len(calls) == 2


@pytest.mark.asyncio
async def test_error_raises():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    directory = OrgDirectory("http://sentinel", "svc-key", transport=httpx.MockTransport(handler))
    with pytest.raises(httpx.HTTPStatusError):
        await directory.list_orgs()
