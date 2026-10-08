"""Short labels: admin overrides of how ontology terms read inside protocol names."""

from tests.api._protocols import seed_protocol_categories

MTB = {
    "term_id": "http://purl.bioontology.org/ontology/NCBITAXON/1773",
    "label": "Mycobacterium tuberculosis",
    "ontology_source": "NCBITAXON",
}


async def _mtb_protocol(client):
    await seed_protocol_categories(client)
    body = {
        "category": "Growth inhibition",
        "protocol_type": "whole_cell",
        "readout_definitions": [{"name": "Signal", "data_type": "numeric"}],
        "ontology_annotations": {"organism": [MTB]},
    }
    r = await client.post("/api/v1/protocols", json=body)
    assert r.status_code == 201, r.text


async def test_terms_in_use_show_default_and_override(client):
    await _mtb_protocol(client)
    terms = (await client.get("/api/v1/naming-labels/terms-in-use")).json()
    mtb = next(t for t in terms if t["term_id"] == MTB["term_id"])
    assert mtb["slot"] == "organism" and mtb["default_short_label"] == "M. tuberculosis"
    assert mtb["override_short_label"] is None and mtb["protocol_count"] == 1

    body = {
        "term_id": MTB["term_id"],
        "term_label": MTB["label"],
        "ontology_source": "NCBITAXON",
        "short_label": "Mtb",
    }
    r = await client.post("/api/v1/naming-labels", json=body)
    assert r.status_code == 201, r.text
    terms = (await client.get("/api/v1/naming-labels/terms-in-use")).json()
    mtb = next(t for t in terms if t["term_id"] == MTB["term_id"])
    assert mtb["override_short_label"] == "Mtb" and mtb["override_id"] == r.json()["id"]


async def test_duplicate_term_conflicts(client):
    body = {
        "term_id": MTB["term_id"],
        "term_label": MTB["label"],
        "ontology_source": "NCBITAXON",
        "short_label": "Mtb",
    }
    assert (await client.post("/api/v1/naming-labels", json=body)).status_code == 201
    assert (await client.post("/api/v1/naming-labels", json=body)).status_code == 409


async def test_update_and_delete(client):
    body = {
        "term_id": MTB["term_id"],
        "term_label": MTB["label"],
        "ontology_source": "NCBITAXON",
        "short_label": "Mtb",
    }
    created = (await client.post("/api/v1/naming-labels", json=body)).json()
    r = await client.patch(f"/api/v1/naming-labels/{created['id']}", json={"short_label": "M. tb"})
    assert r.status_code == 200 and r.json()["short_label"] == "M. tb"
    assert (await client.delete(f"/api/v1/naming-labels/{created['id']}")).status_code == 204
    assert (await client.get("/api/v1/naming-labels")).json() == []


async def test_editor_cannot_write(editor_client):
    body = {
        "term_id": MTB["term_id"],
        "term_label": MTB["label"],
        "ontology_source": "NCBITAXON",
        "short_label": "Mtb",
    }
    assert (await editor_client.post("/api/v1/naming-labels", json=body)).status_code == 403
