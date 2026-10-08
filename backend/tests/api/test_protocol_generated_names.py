"""Names are generated: from the category pattern and the facts, never typed."""

import pytest

MTB = {"term_id": "http://purl.bioontology.org/ontology/NCBITAXON/1773", "label": "Mycobacterium tuberculosis", "ontology_source": "NCBITAXON"}
READOUTS = [{"name": "Signal", "data_type": "numeric"}]


@pytest.fixture
async def categories(client):
    assert (await client.post("/api/v1/protocol-categories/defaults")).status_code == 200


def _body(**over):
    body = {
        "protocol_type": "whole_cell", "category": "Growth inhibition", "readout_definitions": READOUTS,
        "ontology_annotations": {"organism": [MTB]},
    }
    return body | over


async def test_create_generates_the_name(client, categories):
    r = await client.post("/api/v1/protocols", json=_body(discriminator="resazurin"))
    assert r.status_code == 201, r.text
    # no home organism set in this workspace: organisms still read as their short label
    assert r.json()["name"] == "M. tuberculosis growth inhibition [resazurin]"


async def test_missing_fact_is_422(client, categories):
    r = await client.post("/api/v1/protocols", json=_body(ontology_annotations={}))
    assert r.status_code == 422 and "organism" in r.text


async def test_second_bare_protocol_is_409_and_names_the_first(client, categories):
    first = (await client.post("/api/v1/protocols", json=_body())).json()
    r = await client.post("/api/v1/protocols", json=_body())
    assert r.status_code == 409 and first["code"] in r.text


async def test_discriminator_resolves_and_flags_the_bare_one(client, categories):
    bare = (await client.post("/api/v1/protocols", json=_body())).json()
    r = await client.post("/api/v1/protocols", json=_body(discriminator="OD600"))
    assert r.status_code == 201
    again = (await client.get(f"/api/v1/protocols/{bare['id']}")).json()
    assert again["name_flag"] == "needs_discriminator"


async def test_name_field_is_rejected(client, categories):
    assert (await client.post("/api/v1/protocols", json=_body(name="My name"))).status_code == 422


async def test_changing_the_organism_renames_and_keeps_the_old_name_as_alias(client, categories):
    p = (await client.post("/api/v1/protocols", json=_body(discriminator="resazurin"))).json()
    smeg = {"term_id": "http://purl.bioontology.org/ontology/NCBITAXON/1772", "label": "Mycolicibacterium smegmatis", "ontology_source": "NCBITAXON"}
    r = await client.put(f"/api/v1/protocols/{p['id']}/ontology-annotations", json={"slot": "organism", "terms": [smeg]})
    assert r.json()["name"] == "M. smegmatis growth inhibition [resazurin]"
    assert r.json()["aliases"][0]["label"] == "M. tuberculosis growth inhibition [resazurin]"


async def test_discriminator_route(client, categories):
    p = (await client.post("/api/v1/protocols", json=_body())).json()
    r = await client.put(f"/api/v1/protocols/{p['id']}/discriminator", json={"discriminator": "OD600"})
    assert r.json()["name"] == "M. tuberculosis growth inhibition [OD600]"
    assert (await client.put(f"/api/v1/protocols/{p['id']}/discriminator", json={"discriminator": "HTS"})).status_code == 422


async def test_publish_refused_while_incomplete(client, categories):
    p = (await client.post("/api/v1/protocols", json=_body())).json()
    await client.delete(f"/api/v1/protocols/{p['id']}/ontology-annotations/organism")
    assert (await client.post(f"/api/v1/protocols/{p['id']}/publish")).status_code == 409
