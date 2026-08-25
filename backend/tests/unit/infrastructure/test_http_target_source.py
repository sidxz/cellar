"""HttpTargetSource — pages through prot-cellar's target list, forwarding auth."""

from __future__ import annotations

import uuid

import httpx
import pytest

from cellar.application.screening.target_source import SourceTarget
from cellar.domain.shared.errors import AuthorizationError, ServiceUnavailableError
from cellar.infrastructure.prot_cellar.settings import ProtCellarSettings
from cellar.infrastructure.prot_cellar.target_source import HttpTargetSource

ORG_ID = str(uuid.uuid4())
T1, T2, T3 = (str(uuid.uuid4()) for _ in range(3))
HEADERS = {"authorization": "Bearer idp", "x-authz-token": "authz"}


def _target(tid: str, name: str, ttype: str = "single_protein", org: str | None = ORG_ID):
    return {
        "id": tid,
        "workspace_id": str(uuid.uuid4()),
        "pref_name": name,
        "target_type": ttype,
        "components": [],
        "organism_id": org,
        "chembl_id": "CHEMBL1" if name == "AspS" else None,
        "chembl_url": None,
        "pharmacological_class": None,
        "cross_references": [],
        "version": 2,
    }


def _source(handler) -> HttpTargetSource:
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return HttpTargetSource(client, ProtCellarSettings(url="http://prot", _env_file=None))


@pytest.mark.asyncio
async def test_pages_until_cursor_exhausted_and_forwards_auth_headers():
    calls: list[httpx.Request] = []

    def handler(req: httpx.Request) -> httpx.Response:
        calls.append(req)
        assert req.headers["authorization"] == "Bearer idp"
        assert req.headers["x-authz-token"] == "authz"
        if req.url.path == "/api/v1/targets":
            assert req.url.params["limit"] == "200"
            cursor = req.url.params.get("cursor")
            if cursor is None:
                return httpx.Response(
                    200,
                    json={
                        "items": [_target(T1, "AspS"), _target(T2, "ClpC1")],
                        "next_cursor": T2,
                    },
                )
            assert cursor == T2
            return httpx.Response(
                200,
                json={
                    "items": [_target(T3, "Weird", ttype="martian")],
                    "next_cursor": None,
                },
            )
        if req.url.path == f"/api/v1/organisms/{ORG_ID}":
            return httpx.Response(
                200,
                json={
                    "id": ORG_ID,
                    "scientific_name": "Mycobacterium tuberculosis",
                },
            )
        raise AssertionError(f"unexpected {req.url}")

    result = await _source(handler).fetch_all(forwarded_headers=HEADERS)

    assert result == [
        SourceTarget(
            uuid.UUID(T1),
            "AspS",
            "single_protein",
            "Mycobacterium tuberculosis",
            "CHEMBL1",
            2,
        ),
        SourceTarget(
            uuid.UUID(T2),
            "ClpC1",
            "single_protein",
            "Mycobacterium tuberculosis",
            None,
            2,
        ),
        SourceTarget(
            uuid.UUID(T3),
            "Weird",
            "unknown",
            "Mycobacterium tuberculosis",
            None,
            2,
        ),
    ]
    # 2 target pages + exactly ONE organism lookup (cached per fetch_all).
    assert [c.url.path for c in calls].count(f"/api/v1/organisms/{ORG_ID}") == 1
    assert len(calls) == 3


@pytest.mark.asyncio
async def test_organism_lookup_failure_degrades_to_none():
    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path == "/api/v1/targets":
            return httpx.Response(200, json={"items": [_target(T1, "AspS")], "next_cursor": None})
        return httpx.Response(500)

    [t] = await _source(handler).fetch_all(forwarded_headers=HEADERS)
    assert t.organism is None


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [401, 403])
async def test_auth_rejection_raises_authorization_error(status: int):
    src = _source(lambda req: httpx.Response(status, json={"detail": "editor required"}))
    with pytest.raises(AuthorizationError, match="editor"):
        await src.fetch_all(forwarded_headers=HEADERS)


@pytest.mark.asyncio
async def test_unreachable_raises_service_unavailable():
    def handler(req: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom", request=req)

    with pytest.raises(ServiceUnavailableError, match="prot-cellar"):
        await _source(handler).fetch_all(forwarded_headers=HEADERS)


@pytest.mark.asyncio
async def test_5xx_raises_service_unavailable():
    src = _source(lambda req: httpx.Response(502))
    with pytest.raises(ServiceUnavailableError):
        await src.fetch_all(forwarded_headers=HEADERS)
