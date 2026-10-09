"""GET /ontology/search?exact_only=true: only the exact group comes back."""

import pytest

from cellar.application.screening.search_ontology import SearchOntology
from cellar.domain.shared.ontology import OntologyTerm
from cellar.interface.dependencies._workspace_config import SearchOntologyDep

HEP = OntologyTerm(term_id="http://x/hep", label="Hep G2 cell", ontology_source="CLO")
PARTIAL = OntologyTerm(term_id="http://x/luc", label="HepG2-AhR-luc", ontology_source="CLO")


class _FakeBioPortal:
    async def search(self, *, exact_only=False, **kwargs):
        return [HEP] if exact_only else [HEP, PARTIAL]


@pytest.fixture
def fake_search(api_app):
    dep = SearchOntologyDep.__metadata__[0].dependency
    api_app.dependency_overrides[dep] = lambda: SearchOntology(_FakeBioPortal())
    yield
    api_app.dependency_overrides.pop(dep, None)


async def test_exact_only_returns_the_exact_group(client, fake_search):
    params = {"q": "HepG2", "ontologies": "CLO"}
    full = await client.get("/api/v1/ontology/search", params=params)
    assert [t["label"] for t in full.json()] == ["Hep G2 cell", "HepG2-AhR-luc"]
    r = await client.get("/api/v1/ontology/search", params={**params, "exact_only": "true"})
    assert r.status_code == 200, r.text
    assert [t["term_id"] for t in r.json()] == ["http://x/hep"]


async def test_exact_only_common_name_resolves_locally(client, fake_search):
    r = await client.get(
        "/api/v1/ontology/search",
        params={"q": "mouse", "ontologies": "NCBITAXON", "exact_only": "true"},
    )
    assert r.status_code == 200, r.text
    assert [t["label"] for t in r.json()] == ["Mus musculus"]
