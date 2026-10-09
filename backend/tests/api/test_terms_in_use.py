"""GET /ontology/terms-in-use: the terms protocols already use in one annotation slot."""

from tests.api._protocols import seed_protocol_categories

MTB = {
    "term_id": "http://purl.bioontology.org/ontology/NCBITAXON/1773",
    "label": "Mycobacterium tuberculosis",
    "ontology_source": "NCBITAXON",
    "uri": "http://purl.bioontology.org/ontology/NCBITAXON/1773",
}
STRAIN = {"term_id": "free_text:H37Rv", "label": "H37Rv", "ontology_source": "free_text"}


async def _protocol(client, annotations, discriminator=None):
    body = {
        "category": "Growth inhibition",
        "protocol_type": "whole_cell",
        "readout_definitions": [{"name": "Signal", "data_type": "numeric"}],
        "ontology_annotations": annotations,
        "discriminator": discriminator,
    }
    r = await client.post("/api/v1/protocols", json=body)
    assert r.status_code == 201, r.text


async def test_shared_term_listed_once_with_count(client):
    await seed_protocol_categories(client)
    await _protocol(client, {"organism": [MTB], "strain": [STRAIN]}, "resazurin")
    await _protocol(client, {"organism": [MTB]}, "OD600")

    r = await client.get("/api/v1/ontology/terms-in-use", params={"slot": "organism"})
    assert r.status_code == 200, r.text
    assert r.json() == [
        {
            "term_id": MTB["term_id"],
            "label": MTB["label"],
            "ontology_source": "NCBITAXON",
            "uri": MTB["uri"],
            "short_label": "M. tuberculosis",
            "protocol_count": 2,
        }
    ]

    strain = (await client.get("/api/v1/ontology/terms-in-use", params={"slot": "strain"})).json()
    assert [(t["label"], t["short_label"], t["protocol_count"], t["uri"]) for t in strain] == [
        ("H37Rv", "H37Rv", 1, None)
    ]


async def test_short_label_is_the_admin_override(client):
    await seed_protocol_categories(client)
    await _protocol(client, {"organism": [MTB]})
    r = await client.post(
        "/api/v1/naming-labels",
        json={
            "term_id": MTB["term_id"],
            "term_label": MTB["label"],
            "ontology_source": "NCBITAXON",
            "short_label": "Mtb",
        },
    )
    assert r.status_code == 201, r.text
    terms = (await client.get("/api/v1/ontology/terms-in-use", params={"slot": "organism"})).json()
    assert terms[0]["short_label"] == "Mtb"


async def test_viewer_can_read(viewer_client):
    r = await viewer_client.get("/api/v1/ontology/terms-in-use", params={"slot": "organism"})
    assert r.status_code == 200 and r.json() == []
