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


def _hit(term_id: str, label: str, synonyms: list[str] | None = None) -> dict:
    return {
        "@id": term_id,
        "prefLabel": label,
        "synonym": synonyms or [],
        "links": {"ontology": "https://data.bioontology.org/ontologies/CLO"},
    }


async def _search_labels(query: str, collection: list[dict]) -> list[str]:
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(request.url.params)
        return httpx.Response(200, json={"collection": collection})

    terms = await _client(handler).search(query, ["CLO"], workspace_id=WS)
    assert seen["include"] == "prefLabel,synonym"
    return [t.label for t in terms]


@pytest.mark.asyncio
async def test_search_synonym_match_ranks_first():
    labels = await _search_labels(
        "HepG2",
        [
            _hit("http://x/1", "HepG2-AhR-luc"),
            _hit("http://x/2", "ARE-bla HepG2"),
            _hit("http://x/3", "HepG2-CYP2B6-hCAR"),
            _hit("http://x/4", "Hep G2 cell", ["HepG2", "Hep-G2"]),
        ],
    )
    assert labels == ["Hep G2 cell", "HepG2-AhR-luc", "ARE-bla HepG2", "HepG2-CYP2B6-hCAR"]


@pytest.mark.asyncio
async def test_search_exact_preflabel_ranks_first_ignoring_case_and_punctuation():
    labels = await _search_labels(
        "mus musculus",
        [
            _hit("http://x/1", "Mus musculus musculus"),
            _hit("http://x/2", "Mus musculus"),
        ],
    )
    assert labels == ["Mus musculus", "Mus musculus musculus"]


@pytest.mark.asyncio
async def test_search_without_exact_match_keeps_bioportal_order():
    labels = await _search_labels(
        "kinase",
        [_hit("http://x/1", "kinase assay"), _hit("http://x/2", "protein kinase", ["PK"])],
    )
    assert labels == ["kinase assay", "protein kinase"]


@pytest.mark.asyncio
async def test_has_api_key_follows_the_search_resolution_rule(monkeypatch):
    handler = lambda request: httpx.Response(200, json={})  # noqa: E731
    monkeypatch.delenv("BIOPORTAL_API_KEY", raising=False)
    assert await _client(handler, key=None).has_api_key(WS) is False
    assert await _client(handler, key="k").has_api_key(WS) is True
    monkeypatch.setenv("BIOPORTAL_API_KEY", "from-env")
    assert await _client(handler, key=None).has_api_key(WS) is True


@pytest.mark.asyncio
async def test_search_exact_only_returns_just_the_exact_group():
    collection = [
        _hit("http://x/1", "HepG2-AhR-luc"),
        _hit("http://x/4", "Hep G2 cell", ["HepG2"]),
        _hit("http://x/2", "ARE-bla HepG2"),
    ]
    client = _client(lambda r: httpx.Response(200, json={"collection": collection}))
    terms = await client.search("HepG2", ["CLO"], workspace_id=WS, exact_only=True)
    assert [t.label for t in terms] == ["Hep G2 cell"]
    none = await client.search("kinase", ["CLO"], workspace_id=WS, exact_only=True)
    assert none == []
