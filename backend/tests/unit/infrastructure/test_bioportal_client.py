"""BioPortalClient — descendant paging, leaf concepts, failures that must not read as no-terms."""

import uuid

import httpx
import pytest

from cellar.domain.shared.errors import ServiceUnavailableError
from cellar.infrastructure.external.bioportal.client import BioPortalClient

WS = uuid.uuid4()
BAO = "http://www.bioassayontology.org/bao#"


class _Secrets:
    def __init__(self, key: str | None) -> None:
        self._key = key

    async def get_secret(self, name: str) -> str | None:
        return self._key


def _client(handler, key: str | None = "k") -> BioPortalClient:
    return BioPortalClient(_Secrets(key), transport=httpx.MockTransport(handler))


def _term(n: int) -> dict:
    return {"@id": f"{BAO}BAO_{n:07d}", "prefLabel": f"term {n:03d}"}


@pytest.mark.asyncio
async def test_descendants_follow_every_page(monkeypatch):
    monkeypatch.delenv("BIOPORTAL_API_KEY", raising=False)
    pages = {1: [_term(1), _term(2)], 2: [_term(3)]}

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "apikey token=k"
        page = int(request.url.params["page"])
        return httpx.Response(200, json={"collection": pages[page], "pageCount": 2})

    terms = await _client(handler).list_descendants("BAO", f"{BAO}BAO_0000019", workspace_id=WS)
    assert [t.label for t in terms] == ["term 001", "term 002", "term 003"]
    assert {t.ontology_source for t in terms} == {"BAO"}


@pytest.mark.asyncio
async def test_leaf_concept_bare_list_is_empty_not_a_crash():
    terms = await _client(lambda r: httpx.Response(200, json=[])).list_descendants(
        "BAO", f"{BAO}BAO_0000005", workspace_id=WS
    )
    assert terms == []


@pytest.mark.asyncio
async def test_missing_key_raises(monkeypatch):
    monkeypatch.delenv("BIOPORTAL_API_KEY", raising=False)
    client = _client(lambda r: httpx.Response(200, json={"collection": []}), key=None)
    with pytest.raises(ServiceUnavailableError, match="BioPortal API key"):
        await client.search("fluorescence", ["BAO"], workspace_id=WS)


@pytest.mark.asyncio
async def test_http_failure_raises():
    client = _client(lambda r: httpx.Response(401, json={"errors": ["bad key"]}))
    with pytest.raises(ServiceUnavailableError, match="BioPortal lookup failed"):
        await client.search("fluorescence", ["BAO"], workspace_id=WS)
