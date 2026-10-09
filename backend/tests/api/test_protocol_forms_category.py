"""Forms serve a category over the API."""

import uuid

from tests.api._protocols import seed_protocol_categories


async def test_form_round_trips_category_and_keeps_template_fields(client):
    await seed_protocol_categories(client)
    enzyme = next(
        c
        for c in (await client.get("/api/v1/protocol-categories")).json()
        if c["label"] == "Enzyme inhibition"
    )
    body = {
        "name": "IC50 dose-response",
        "category_id": enzyme["id"],
        "assay_format_from_target": True,
        "readout_templates": [
            {"name": "Signal", "data_type": "numeric", "normalization": "percent_inhibition"},
            {
                "name": "IC50",
                "data_type": "dose_response",
                "unit": "uM",
                "dose_response_config": {
                    "curve_type": "ic50",
                    "y_readout_name": "Signal",
                    "y_normalization": "percent_inhibition",
                },
            },
        ],
    }
    r = await client.post("/api/v1/protocol-forms", json=body)
    assert r.status_code == 201, r.text
    form = r.json()
    assert form["category_id"] == enzyme["id"] and form["assay_format_from_target"] is True
    assert form["readout_templates"][1]["unit"] == "µM"
    assert form["readout_templates"][1]["dose_response_config"]["curve_type"] == "ic50"


async def test_form_rejects_an_unknown_category_on_create_and_update(client):
    body = {"name": "Kd", "readout_templates": [{"name": "Signal", "data_type": "numeric"}]}
    stranger = str(uuid.uuid4())
    r = await client.post("/api/v1/protocol-forms", json=body | {"category_id": stranger})
    assert r.status_code == 404, r.text

    created = await client.post("/api/v1/protocol-forms", json=body)
    assert created.status_code == 201, created.text
    r = await client.patch(
        f"/api/v1/protocol-forms/{created.json()['id']}", json={"category_id": stranger}
    )
    assert r.status_code == 404, r.text

    forms = (await client.get("/api/v1/protocol-forms")).json()
    assert [(f["name"], f["category_id"]) for f in forms] == [("Kd", None)]
