"""SearchOntology: common organism names/abbreviations resolve locally for NCBITaxon."""

import uuid

from cellar.application.screening.search_ontology import SearchOntology, SearchOntologyQuery
from cellar.domain.shared.errors import ServiceUnavailableError
from cellar.domain.shared.ontology import OntologyTerm
from tests.fakes.fake_auth import FakeAuth

WS = uuid.uuid4()
MOUSE_URI = "http://purl.bioontology.org/ontology/NCBITAXON/10090"


class _FakeSearch:
    def __init__(self, results=None, fail=False):
        self.results = results or []
        self.fail = fail
        self.calls = 0

    async def search(self, **kwargs):
        self.calls += 1
        if self.fail:
            raise ServiceUnavailableError("BioPortal down")
        return self.results


def _auth():
    return FakeAuth(role="viewer", workspace_id=WS)


async def _search(fake, q, sources):
    result = await SearchOntology(fake)(
        SearchOntologyQuery(workspace_id=WS, query=q, ontology_sources=sources), auth=_auth()
    )
    return result


async def test_mouse_first_even_when_bioportal_fails():
    result = await _search(_FakeSearch(fail=True), "mouse", ["NCBITAXON"])
    terms = result.unwrap()
    assert [(t.term_id, t.label, t.ontology_source, t.uri) for t in terms] == [
        (MOUSE_URI, "Mus musculus", "NCBITAXON", MOUSE_URI)
    ]


async def test_abbreviation_is_case_and_space_insensitive():
    terms = (await _search(_FakeSearch(), "  Mtb ", ["ncbitaxon"])).unwrap()
    assert terms[0].label == "Mycobacterium tuberculosis"
    assert terms[0].term_id.endswith("/NCBITAXON/1773")


async def test_local_hit_precedes_bioportal_and_replaces_duplicate():
    other = OntologyTerm(
        term_id="http://x/other", label="Mouse thing", ontology_source="NCBITAXON"
    )
    dup = OntologyTerm(term_id=MOUSE_URI, label="Mus musculus", ontology_source="NCBITAXON")
    terms = (await _search(_FakeSearch([other, dup]), "mouse", ["NCBITAXON"])).unwrap()
    assert [t.term_id for t in terms] == [MOUSE_URI, "http://x/other"]


async def test_no_source_filter_includes_local_hits():
    terms = (await _search(_FakeSearch(), "human", [])).unwrap()
    assert terms[0].label == "Homo sapiens"


async def test_other_ontologies_unaffected():
    fake = _FakeSearch()
    assert (await _search(fake, "mouse", ["CLO"])).unwrap() == []


async def test_label_is_not_an_alias_and_no_hit_still_fails_when_bioportal_down():
    assert (await _search(_FakeSearch(), "Mus musculus", ["NCBITAXON"])).unwrap() == []
    result = await _search(_FakeSearch(fail=True), "zzz", ["NCBITAXON"])
    assert isinstance(result.failure(), ServiceUnavailableError)


async def test_subtree_scoped_search_skips_local_hits():
    result = await SearchOntology(_FakeSearch())(
        SearchOntologyQuery(
            workspace_id=WS, query="mouse", ontology_sources=["NCBITAXON"], subtree_root_id="r"
        ),
        auth=_auth(),
    )
    assert result.unwrap() == []


async def _exact(fake, q, sources):
    return await SearchOntology(fake)(
        SearchOntologyQuery(workspace_id=WS, query=q, ontology_sources=sources, exact_only=True),
        auth=_auth(),
    )


class _ExactFake(_FakeSearch):
    """Records the exact_only flag; returns `results` as the BioPortal exact group."""

    async def search(self, **kwargs):
        self.exact_only = kwargs.get("exact_only")
        return await super().search(**kwargs)


async def test_exact_only_returns_local_hit_without_asking_bioportal():
    fake = _ExactFake([OntologyTerm(term_id="http://x/1", label="mouse", ontology_source="X")])
    terms = (await _exact(fake, "mouse", ["NCBITAXON"])).unwrap()
    assert [t.term_id for t in terms] == [MOUSE_URI]
    assert fake.calls == 0


async def test_exact_only_without_local_hit_returns_bioportal_exact_group():
    hep = OntologyTerm(term_id="http://x/hep", label="Hep G2 cell", ontology_source="CLO")
    fake = _ExactFake([hep])
    terms = (await _exact(fake, "HepG2", ["CLO"])).unwrap()
    assert terms == [hep]
    assert fake.exact_only is True


async def test_default_search_asks_for_the_full_list():
    fake = _ExactFake()
    await _search(fake, "kinase", ["CLO"])
    assert fake.exact_only is False
