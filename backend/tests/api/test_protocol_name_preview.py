"""Live name preview (create dialog) and discriminator suggestions."""

MTB = {
    "term_id": "http://purl.bioontology.org/ontology/NCBITAXON/1773",
    "label": "Mycobacterium tuberculosis",
    "ontology_source": "NCBITAXON",
}


async def test_preview_renders_and_reports_missing(client):
    await client.post("/api/v1/protocol-categories/defaults")
    r = await client.post(
        "/api/v1/protocols/name-preview",
        json={
            "category": "Growth inhibition",
            "target_ids": [],
            "ontology_annotations": {},
            "discriminator": None,
        },
    )
    body = r.json()
    assert (
        r.status_code == 200
        and body["missing"] == ["organism"]
        and body["missing_labels"] == ["an organism"]
    )
    r = await client.post(
        "/api/v1/protocols/name-preview",
        json={
            "category": "Growth inhibition",
            "target_ids": [],
            "ontology_annotations": {"organism": [MTB]},
            "discriminator": "HTS",
        },
    )
    assert (
        r.json()["discriminator_error"] and r.json()["name"] == "M. tuberculosis growth inhibition"
    )


async def test_preview_reports_a_clash_and_excludes_itself(client):
    await client.post("/api/v1/protocol-categories/defaults")
    body = {
        "protocol_type": "whole_cell",
        "category": "Growth inhibition",
        "readout_definitions": [{"name": "Signal", "data_type": "numeric"}],
        "ontology_annotations": {"organism": [MTB]},
    }
    p = (await client.post("/api/v1/protocols", json=body)).json()
    q = {
        "category": "Growth inhibition",
        "target_ids": [],
        "ontology_annotations": {"organism": [MTB]},
        "discriminator": None,
    }
    assert (await client.post("/api/v1/protocols/name-preview", json=q)).json()["clash"][
        "code"
    ] == p["code"]
    assert (
        await client.post("/api/v1/protocols/name-preview", json=q | {"protocol_id": p["id"]})
    ).json()["clash"] is None


async def test_discriminator_suggestions(client):
    await client.post("/api/v1/protocol-categories/defaults")
    body = {
        "protocol_type": "whole_cell",
        "category": "Growth inhibition",
        "readout_definitions": [{"name": "Signal", "data_type": "numeric"}],
        "ontology_annotations": {"organism": [MTB]},
        "discriminator": "resazurin",
    }
    await client.post("/api/v1/protocols", json=body)
    r = await client.get(
        "/api/v1/protocols/discriminators", params={"base": "M. tuberculosis growth inhibition"}
    )
    assert r.json() == ["resazurin"]
