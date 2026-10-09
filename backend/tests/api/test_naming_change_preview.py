"""Admin naming edits (patterns, short labels, home organism) preview and apply relabels."""

MTB = {"term_id": "http://purl.bioontology.org/ontology/NCBITAXON/1773", "label": "Mycobacterium tuberculosis", "ontology_source": "NCBITAXON"}


async def _setup(client):
    cats = (await client.post("/api/v1/protocol-categories/defaults")).json()
    body = {"protocol_type": "whole_cell", "category": "Growth inhibition", "readout_definitions": [{"name": "Signal", "data_type": "numeric"}], "ontology_annotations": {"organism": [MTB]}}
    a = (await client.post("/api/v1/protocols", json=body | {"discriminator": "resazurin"})).json()
    b = (await client.post("/api/v1/protocols", json=body | {"discriminator": "OD600"})).json()
    growth = next(c for c in cats if c["label"] == "Growth inhibition")
    return growth, a, b


async def test_label_override_preview_and_apply(client):
    _, a, _ = await _setup(client)
    req = {"kind": "label", "term_id": MTB["term_id"], "term_label": MTB["label"], "ontology_source": "NCBITAXON", "short_label": "Mtb"}
    preview = (await client.post("/api/v1/protocol-names/preview-change", json=req)).json()
    assert {(c["before"], c["after"]) for c in preview["changes"]} >= {("M. tuberculosis growth inhibition [resazurin]", "Mtb growth inhibition [resazurin]")}
    assert preview["collisions"] == []
    r = await client.post("/api/v1/naming-labels", json={k: req[k] for k in ("term_id", "term_label", "ontology_source", "short_label")})
    assert r.status_code == 201
    assert (await client.get(f"/api/v1/protocols/{a['id']}")).json()["name"] == "Mtb growth inhibition [resazurin]"


async def test_pattern_edit_that_collides_is_refused(client):
    cats = (await client.post("/api/v1/protocol-categories/defaults")).json()
    bactericidal = next(c for c in cats if c["label"] == "Bactericidal activity")
    base = {"protocol_type": "whole_cell", "readout_definitions": [{"name": "Signal", "data_type": "numeric"}], "ontology_annotations": {"organism": [MTB]}, "discriminator": "resazurin"}
    a = (await client.post("/api/v1/protocols", json=base | {"category": "Growth inhibition"})).json()
    c = (await client.post("/api/v1/protocols", json=base | {"category": "Bactericidal activity"})).json()
    req = {"kind": "category", "category_id": bactericidal["id"], "name_pattern": "{organism} growth inhibition"}
    preview = (await client.post("/api/v1/protocol-names/preview-change", json=req)).json()
    assert set(preview["collisions"][0]["codes"]) == {a["code"], c["code"]}
    r = await client.patch(f"/api/v1/protocol-categories/{bactericidal['id']}", json={"name_pattern": "{organism} growth inhibition"})
    assert r.status_code == 409


async def test_home_organism_drops_the_prefix(client, make_target):
    await client.post("/api/v1/protocol-categories/defaults")
    target = await make_target("PptT", organism="Mycobacterium tuberculosis")
    body = {"protocol_type": "biochemical", "category": "Enzyme inhibition", "readout_definitions": [{"name": "Signal", "data_type": "numeric"}], "target_ids": [target]}
    p = (await client.post("/api/v1/protocols", json=body)).json()
    assert p["name"] == "M. tuberculosis PptT inhibition"
    preview = (await client.post("/api/v1/protocol-names/preview-change", json={"kind": "home_organism", "terms": [MTB]})).json()
    assert ("M. tuberculosis PptT inhibition", "PptT inhibition") in {(x["before"], x["after"]) for x in preview["changes"]}
    still = (await client.get(f"/api/v1/protocols/{p['id']}")).json()["name"]
    assert still == "M. tuberculosis PptT inhibition"  # preview renames nothing
    assert (await client.put("/api/v1/settings/home-organism", json={"terms": [MTB]})).status_code == 200
    assert (await client.get(f"/api/v1/protocols/{p['id']}")).json()["name"] == "PptT inhibition"


async def test_a_relabel_that_swaps_two_names_applies_cleanly(client, make_target):
    await client.post("/api/v1/protocol-categories/defaults")
    human = {"term_id": "http://purl.bioontology.org/ontology/NCBITAXON/9606", "label": "Homo sapiens", "ontology_source": "NCBITAXON"}
    assert (await client.put("/api/v1/settings/home-organism", json={"terms": [MTB]})).status_code == 200
    mtb_dhfr = await make_target("DHFR", organism="Mycobacterium tuberculosis")
    human_dhfr = await make_target("DHFR", organism="Homo sapiens")
    body = {"protocol_type": "biochemical", "category": "Enzyme inhibition", "readout_definitions": [{"name": "Signal", "data_type": "numeric"}]}
    a = (await client.post("/api/v1/protocols", json=body | {"target_ids": [mtb_dhfr]})).json()
    b = (await client.post("/api/v1/protocols", json=body | {"target_ids": [human_dhfr]})).json()
    assert (a["name"], b["name"]) == ("DHFR inhibition", "Human DHFR inhibition")

    preview = (await client.post("/api/v1/protocol-names/preview-change", json={"kind": "home_organism", "terms": [human]})).json()
    assert preview["collisions"] == []
    r = await client.put("/api/v1/settings/home-organism", json={"terms": [human]})
    assert r.status_code == 200, r.text
    a2 = (await client.get(f"/api/v1/protocols/{a['id']}")).json()
    b2 = (await client.get(f"/api/v1/protocols/{b['id']}")).json()
    assert (a2["name"], b2["name"]) == ("M. tuberculosis DHFR inhibition", "DHFR inhibition")
    assert (a2["name_flag"], b2["name_flag"]) == (None, None)


HUMAN = {
    "term_id": "http://purl.bioontology.org/ontology/NCBITAXON/9606",
    "label": "Homo sapiens",
    "ontology_source": "NCBITAXON",
}
PREVIEW = "/api/v1/protocol-names/preview-change"
HOME = "/api/v1/settings/home-organism"


async def _name(client, protocol):
    return (await client.get(f"/api/v1/protocols/{protocol['id']}")).json()["name"]


async def test_several_home_organisms_name_both_without_a_prefix(client, make_target):
    await client.post("/api/v1/protocol-categories/defaults")
    inha = await make_target("InhA", organism="Mycobacterium tuberculosis")
    herg = await make_target("hERG", organism="Homo sapiens")
    body = {
        "protocol_type": "biochemical",
        "category": "Enzyme inhibition",
        "readout_definitions": [{"name": "Signal", "data_type": "numeric"}],
    }
    a = (await client.post("/api/v1/protocols", json=body | {"target_ids": [inha]})).json()
    b = (await client.post("/api/v1/protocols", json=body | {"target_ids": [herg]})).json()
    assert (a["name"], b["name"]) == ("M. tuberculosis InhA inhibition", "Human hERG inhibition")

    req = {"kind": "home_organism", "terms": [MTB, HUMAN]}
    preview = (await client.post(PREVIEW, json=req)).json()
    assert {(x["before"], x["after"]) for x in preview["changes"]} == {
        ("M. tuberculosis InhA inhibition", "InhA inhibition"),
        ("Human hERG inhibition", "hERG inhibition"),
    }
    # nothing is renamed before confirm
    assert await _name(client, a) == "M. tuberculosis InhA inhibition"
    assert await _name(client, b) == "Human hERG inhibition"

    r = await client.put(HOME, json={"terms": [MTB, HUMAN]})
    assert r.status_code == 200, r.text
    naming = r.json()["protocol_naming"]
    assert [t["label"] for t in naming["home_organisms"]] == [MTB["label"], HUMAN["label"]]
    assert "home_organism" not in naming
    assert await _name(client, a) == "InhA inhibition"
    assert await _name(client, b) == "hERG inhibition"


async def test_the_single_term_shape_is_still_accepted(client):
    r = await client.put(HOME, json={"term": MTB})
    assert r.status_code == 200, r.text
    assert [t["label"] for t in r.json()["protocol_naming"]["home_organisms"]] == [MTB["label"]]
    preview = await client.post(PREVIEW, json={"kind": "home_organism", "term": MTB})
    assert preview.status_code == 200, preview.text
    cleared = await client.put(HOME, json={"term": None})
    assert cleared.status_code == 200
    assert cleared.json()["protocol_naming"].get("home_organisms") in (None, [])


async def test_a_home_organism_request_needs_a_list_or_a_term(client):
    assert (await client.put(HOME, json={})).status_code == 422
