"""HttpTargetSource — pages through prot-cellar's target list, forwarding auth."""

from __future__ import annotations

import json
import uuid

import httpx
import pytest

from cellar.application.screening.target_source import NewTarget, SourceTarget
from cellar.domain.shared.errors import (
    AuthorizationError,
    ConflictError,
    NotFoundError,
    ServiceUnavailableError,
    ValidationError,
)
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


@pytest.mark.asyncio
async def test_3xx_raises_service_unavailable():
    """Any non-2xx that isn't a 401/403 is a source failure, not a 500 (Critical 1)."""
    src = _source(lambda req: httpx.Response(302))
    with pytest.raises(ServiceUnavailableError):
        await src.fetch_all(forwarded_headers=HEADERS)


@pytest.mark.asyncio
async def test_non_json_response_raises_service_unavailable():
    """A 200 with an unparseable body must not raise a raw JSONDecodeError (Critical 1)."""
    src = _source(lambda req: httpx.Response(200, content=b"not json"))
    with pytest.raises(ServiceUnavailableError):
        await src.fetch_all(forwarded_headers=HEADERS)


# ---------------------------------------------------------------------------
# create_target — request a new target in prot-cellar (task E2)
# ---------------------------------------------------------------------------

PROTEIN_ID = str(uuid.uuid4())
NEW_ID = str(uuid.uuid4())


def _request(**overrides) -> NewTarget:
    fields = {
        "name": "hERG",
        "target_type": "single_protein",
        "organism_tax_id": 9606,
        "organism_label": "Homo sapiens",
        "chembl_id": "CHEMBL240",
        "protein_identifier": "Q12809",
    }
    return NewTarget(**{**fields, **overrides})


def _create_handler(calls: list[httpx.Request], *, post_status: int = 201, post_json=None):
    def handler(req: httpx.Request) -> httpx.Response:
        calls.append(req)
        path = req.url.path
        if path == "/api/v1/organisms/resolve/9606":
            return httpx.Response(200, json={"id": ORG_ID, "scientific_name": "Homo sapiens"})
        if path == "/api/v1/proteins/resolve/Q12809":
            return httpx.Response(200, json={"id": PROTEIN_ID, "primary_accession": "Q12809"})
        if path == "/api/v1/targets" and req.method == "POST":
            body = json.loads(req.content)
            return httpx.Response(
                post_status,
                json=post_json
                if post_json is not None
                else {
                    **_target(NEW_ID, body["pref_name"], ttype=body["target_type"]),
                    "chembl_id": body["chembl_id"],
                    "version": 1,
                },
            )
        raise AssertionError(f"unexpected {req.method} {req.url}")

    return handler


@pytest.mark.asyncio
async def test_create_resolves_organism_and_protein_then_posts_with_forwarded_tokens():
    calls: list[httpx.Request] = []
    created = await _source(_create_handler(calls)).create_target(
        _request(), forwarded_headers=HEADERS
    )

    assert [(c.method, c.url.path) for c in calls] == [
        ("GET", "/api/v1/organisms/resolve/9606"),
        ("GET", "/api/v1/proteins/resolve/Q12809"),
        ("POST", "/api/v1/targets"),
    ]
    for c in calls:
        assert c.headers["authorization"] == "Bearer idp"
        assert c.headers["x-authz-token"] == "authz"
    assert json.loads(calls[-1].content) == {
        "pref_name": "hERG",
        "target_type": "single_protein",
        "organism_id": ORG_ID,
        "chembl_id": "CHEMBL240",
        "components": [{"protein_id": PROTEIN_ID, "relationship": "single_protein"}],
    }
    assert created == SourceTarget(
        uuid.UUID(NEW_ID), "hERG", "single_protein", "Homo sapiens", "CHEMBL240", 1
    )


@pytest.mark.asyncio
async def test_create_component_free_type_sends_no_components_and_skips_protein_lookup():
    calls: list[httpx.Request] = []
    await _source(_create_handler(calls)).create_target(
        _request(target_type="cell_line", protein_identifier=None, chembl_id=None),
        forwarded_headers=HEADERS,
    )
    assert [c.url.path for c in calls] == [
        "/api/v1/organisms/resolve/9606",
        "/api/v1/targets",
    ]
    body = json.loads(calls[-1].content)
    assert body["components"] == []
    assert body["chembl_id"] is None


@pytest.mark.asyncio
async def test_create_organism_missing_raises_not_found_naming_the_organism():
    def handler(req: httpx.Request) -> httpx.Response:
        assert req.url.path == "/api/v1/organisms/resolve/9606"
        return httpx.Response(404, json={"error": "NotFoundError", "message": "nope"})

    with pytest.raises(NotFoundError) as exc:
        await _source(handler).create_target(_request(), forwarded_headers=HEADERS)
    assert "Homo sapiens" in exc.value.message
    assert "ProtCellar" in exc.value.message


@pytest.mark.asyncio
async def test_create_protein_missing_raises_not_found():
    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path.startswith("/api/v1/organisms/"):
            return httpx.Response(200, json={"id": ORG_ID, "scientific_name": "Homo sapiens"})
        assert req.method == "GET", "must not POST when the protein is unknown"
        return httpx.Response(404, json={"message": "Protein 'Q12809' not found"})

    with pytest.raises(NotFoundError, match="Protein Q12809 is not in ProtCellar"):
        await _source(handler).create_target(_request(), forwarded_headers=HEADERS)


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [401, 403])
async def test_create_refused_raises_editor_access_message(status: int):
    calls: list[httpx.Request] = []
    src = _source(_create_handler(calls, post_status=status, post_json={"message": "no"}))
    with pytest.raises(AuthorizationError, match="You need editor access in ProtCellar"):
        await src.create_target(_request(), forwarded_headers=HEADERS)


@pytest.mark.asyncio
@pytest.mark.parametrize(("status", "error"), [(409, ConflictError), (422, ValidationError)])
async def test_create_rejection_passes_message_through(status: int, error: type):
    calls: list[httpx.Request] = []
    src = _source(
        _create_handler(
            calls, post_status=status, post_json={"error": "x", "message": "Name already used"}
        )
    )
    with pytest.raises(error, match="Name already used"):
        await src.create_target(_request(), forwarded_headers=HEADERS)


@pytest.mark.asyncio
async def test_create_rejection_without_a_message_gets_a_generic_one():
    calls: list[httpx.Request] = []
    src = _source(
        _create_handler(calls, post_status=422, post_json={"detail": [{"loc": ["body"]}]})
    )
    with pytest.raises(ValidationError, match="ProtCellar rejected"):
        await src.create_target(_request(), forwarded_headers=HEADERS)


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [500, 503])
async def test_create_5xx_raises_service_unavailable(status: int):
    calls: list[httpx.Request] = []
    src = _source(_create_handler(calls, post_status=status, post_json={}))
    with pytest.raises(ServiceUnavailableError):
        await src.create_target(_request(), forwarded_headers=HEADERS)


@pytest.mark.asyncio
async def test_create_unreachable_raises_service_unavailable():
    def handler(req: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("slow", request=req)

    with pytest.raises(ServiceUnavailableError):
        await _source(handler).create_target(_request(), forwarded_headers=HEADERS)


@pytest.mark.asyncio
async def test_create_malformed_success_body_raises_service_unavailable():
    calls: list[httpx.Request] = []
    src = _source(_create_handler(calls, post_json={"unexpected": True}))
    with pytest.raises(ServiceUnavailableError):
        await src.create_target(_request(), forwarded_headers=HEADERS)
