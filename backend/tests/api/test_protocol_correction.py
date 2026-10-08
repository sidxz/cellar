"""Correcting a published protocol: one reason, one rename, same code."""

MTB = {"term_id": "http://purl.bioontology.org/ontology/NCBITAXON/1773", "label": "Mycobacterium tuberculosis", "ontology_source": "NCBITAXON"}
SMEG = {"term_id": "http://purl.bioontology.org/ontology/NCBITAXON/1772", "label": "Mycolicibacterium smegmatis", "ontology_source": "NCBITAXON"}


async def _published(client, **over):
    await client.post("/api/v1/protocol-categories/defaults")
    body = {"protocol_type": "whole_cell", "category": "Growth inhibition", "readout_definitions": [{"name": "Signal", "data_type": "numeric"}], "ontology_annotations": {"organism": [MTB]}, "discriminator": "resazurin"} | over
    p = (await client.post("/api/v1/protocols", json=body)).json()
    assert (await client.post(f"/api/v1/protocols/{p['id']}/publish")).status_code == 200
    return p


async def test_correction_renames_with_reason(client):
    p = await _published(client)
    r = await client.post(f"/api/v1/protocols/{p['id']}/correct", json={"reason": "Strain was always M. smegmatis", "ontology_annotations": {"organism": [SMEG]}})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["name"] == "M. smegmatis growth inhibition [resazurin]" and body["code"] == p["code"]
    assert body["aliases"][0]["reason"] == "Correction: Strain was always M. smegmatis"


async def test_correction_needs_a_reason(client):
    p = await _published(client)
    r = await client.post(f"/api/v1/protocols/{p['id']}/correct", json={"reason": "  ", "discriminator": "OD600"})
    assert r.status_code == 422


async def test_drafts_are_edited_not_corrected(client):
    await client.post("/api/v1/protocol-categories/defaults")
    body = {"protocol_type": "whole_cell", "category": "Growth inhibition", "readout_definitions": [{"name": "Signal", "data_type": "numeric"}], "ontology_annotations": {"organism": [MTB]}}
    p = (await client.post("/api/v1/protocols", json=body)).json()
    assert (await client.post(f"/api/v1/protocols/{p['id']}/correct", json={"reason": "x", "discriminator": "OD600"})).status_code == 409


async def test_correction_cannot_leave_a_published_name_incomplete(client):
    p = await _published(client)
    r = await client.post(f"/api/v1/protocols/{p['id']}/correct", json={"reason": "x", "ontology_annotations": {"organism": []}})
    assert r.status_code == 422


async def test_correction_into_a_clash_is_409(client):
    a = await _published(client)
    b = await _published(client, discriminator="OD600")
    r = await client.post(f"/api/v1/protocols/{b['id']}/correct", json={"reason": "same method", "discriminator": "resazurin"})
    assert r.status_code == 409 and a["code"] in r.text
