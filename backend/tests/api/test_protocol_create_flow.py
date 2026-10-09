"""Create flow over the API: forms, assay format from target, siblings, nicknames."""

import pytest

from tests.api._protocols import seed_protocol_categories

BAO = "http://www.bioassayontology.org/bao#"


async def _enzyme_form(client, *, from_target=True):
    categories = (await client.get("/api/v1/protocol-categories")).json()
    enzyme = next(c for c in categories if c["label"] == "Enzyme inhibition")
    body = {
        "name": "IC50 dose-response",
        "category_id": enzyme["id"],
        "assay_format_from_target": from_target,
        "readout_templates": [{"name": "Signal", "data_type": "numeric"}],
        "ontology_defaults": [
            {
                "slot_name": "assay_format",
                "terms": [
                    {
                        "term_id": f"{BAO}BAO_0000217",
                        "label": "biochemical format",
                        "ontology_source": "BAO",
                    }
                ],
            }
        ],
    }
    r = await client.post("/api/v1/protocol-forms", json=body)
    assert r.status_code == 201, r.text
    return r.json()


def _enzyme_body(form, target_id):
    return {
        "category": "Enzyme inhibition",
        "protocol_type": "biochemical",
        "target_ids": [target_id],
        "form_id": form["id"],
        "readout_definitions": [{"name": "Signal", "data_type": "numeric"}],
    }


@pytest.mark.parametrize(
    ("target_type", "label"),
    [
        ("single_protein", "single protein format"),
        ("protein_complex", "protein complex format"),
    ],
)
async def test_assay_format_follows_the_target(client, make_target, target_type, label):
    await seed_protocol_categories(client)
    form = await _enzyme_form(client)
    target_id = await make_target(
        "PptT", target_type=target_type, organism="Mycobacterium tuberculosis"
    )
    r = await client.post("/api/v1/protocols", json=_enzyme_body(form, target_id))
    assert r.status_code == 201, r.text
    assert r.json()["ontology_annotations"]["assay_format"][0]["label"] == label


async def test_an_unmapped_target_falls_back_to_the_forms_format(client, make_target):
    await seed_protocol_categories(client)
    form = await _enzyme_form(client)
    target_id = await make_target("Mystery", target_type="unknown", organism="Homo sapiens")
    r = await client.post("/api/v1/protocols", json=_enzyme_body(form, target_id))
    assert r.status_code == 201, r.text
    assert r.json()["ontology_annotations"]["assay_format"][0]["label"] == "biochemical format"


async def test_a_form_that_does_not_follow_the_target_leaves_the_format_alone(client, make_target):
    await seed_protocol_categories(client)
    form = await _enzyme_form(client, from_target=False)
    target_id = await make_target("PptT", organism="Mycobacterium tuberculosis")
    r = await client.post("/api/v1/protocols", json=_enzyme_body(form, target_id))
    assert r.status_code == 201, r.text
    assert "assay_format" not in (r.json()["ontology_annotations"] or {})


async def test_without_targets_the_forms_format_applies(client):
    await seed_protocol_categories(client)
    form = await _enzyme_form(client)
    body = {
        "category": "Growth inhibition",
        "protocol_type": "biochemical",
        "form_id": form["id"],
        "readout_definitions": [{"name": "Signal", "data_type": "numeric"}],
        "ontology_annotations": {
            "organism": [
                {
                    "term_id": "http://purl.bioontology.org/ontology/NCBITAXON/1773",
                    "label": "Mycobacterium tuberculosis",
                    "ontology_source": "NCBITAXON",
                }
            ]
        },
    }
    r = await client.post("/api/v1/protocols", json=body)
    assert r.status_code == 201, r.text
    assert r.json()["ontology_annotations"]["assay_format"][0]["label"] == "biochemical format"


async def test_an_unknown_form_is_not_found(client):
    await seed_protocol_categories(client)
    body = {
        "category": "Plasma stability",
        "protocol_type": "biochemical",
        "form_id": "00000000-0000-0000-0000-000000000001",
        "readout_definitions": [{"name": "Signal", "data_type": "numeric"}],
    }
    r = await client.post("/api/v1/protocols", json=body)
    assert r.status_code == 404, r.text


MTB = {
    "term_id": "http://purl.bioontology.org/ontology/NCBITAXON/1773",
    "label": "Mycobacterium tuberculosis",
    "ontology_source": "NCBITAXON",
}


def _growth(**kw):
    return {
        "category": "Growth inhibition",
        "protocol_type": "whole_cell",
        "readout_definitions": [{"name": "MIC", "data_type": "numeric"}],
        "ontology_annotations": {"organism": [MTB]},
        **kw,
    }


async def test_preview_and_create_rename_a_bare_sibling(client):
    await seed_protocol_categories(client)
    first = (await client.post("/api/v1/protocols", json=_growth())).json()
    preview = (
        await client.post(
            "/api/v1/protocols/name-preview",
            json={
                "category": "Growth inhibition",
                "ontology_annotations": {"organism": [MTB]},
                "discriminator": "hypoxia",
                "sibling_discriminators": [{"protocol_id": first["id"], "discriminator": "MABA"}],
            },
        )
    ).json()
    sib = preview["siblings"][0]
    assert sib["status"] == "draft" and sib["is_locked"] is False
    assert preview["sibling_renames"] == [
        {
            "protocol_id": first["id"],
            "code": first["code"],
            "name": "M. tuberculosis growth inhibition [MABA]",
            "error": None,
        }
    ]
    r = await client.post(
        "/api/v1/protocols",
        json=_growth(
            discriminator="hypoxia",
            nicknames=["LORA"],
            sibling_discriminators=[{"protocol_id": first["id"], "discriminator": "MABA"}],
        ),
    )
    assert r.status_code == 201, r.text
    assert (await client.get(f"/api/v1/protocols/{first['id']}")).json()["name"].endswith("[MABA]")


async def test_preview_reports_a_sibling_name_clash(client):
    await seed_protocol_categories(client)
    first = (await client.post("/api/v1/protocols", json=_growth())).json()
    preview = (
        await client.post(
            "/api/v1/protocols/name-preview",
            json={
                "category": "Growth inhibition",
                "ontology_annotations": {"organism": [MTB]},
                "discriminator": "MABA",
                "sibling_discriminators": [{"protocol_id": first["id"], "discriminator": "MABA"}],
            },
        )
    ).json()
    assert preview["sibling_renames"][0]["error"]
