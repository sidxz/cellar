"""Protocol categories: label + name pattern, admin-managed, shipped defaults."""

from cellar.domain.shared.protocol_naming import DEFAULT_CATEGORY_PATTERNS
from cellar.domain.workspace_config.default_protocol_forms import DEFAULT_PROTOCOL_FORMS


async def test_seed_defaults_is_idempotent(client):
    r = await client.post("/api/v1/protocol-categories/defaults")
    assert r.status_code == 200, r.text
    assert len(r.json()) == 47
    forms = (await client.get("/api/v1/protocol-forms")).json()
    assert len(forms) == len(DEFAULT_PROTOCOL_FORMS)
    again = await client.post("/api/v1/protocol-categories/defaults")
    assert len(again.json()) == 47
    assert len((await client.get("/api/v1/protocol-forms")).json()) == len(forms)


async def test_reseeding_keeps_a_stored_pattern_when_the_shipped_one_changes(client, monkeypatch):
    old, new = "{organism} growth inhibition", "{organism} {strain?} growth inhibition"
    monkeypatch.setitem(DEFAULT_CATEGORY_PATTERNS, "Growth inhibition", old)
    await client.post("/api/v1/protocol-categories/defaults")
    monkeypatch.setitem(DEFAULT_CATEGORY_PATTERNS, "Growth inhibition", new)
    cats = (await client.post("/api/v1/protocol-categories/defaults")).json()
    growth = next(c for c in cats if c["label"] == "Growth inhibition")
    assert growth["name_pattern"] == old
    assert growth["default_pattern"] == new


async def test_create_new_category_gets_generic_pattern(client):
    r = await client.post("/api/v1/protocol-categories", json={"label": "Biofilm inhibition"})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["name_pattern"] == "{subject?} biofilm inhibition"
    assert body["default_pattern"] == body["name_pattern"]


async def test_duplicate_label_any_case_conflicts(client):
    await client.post("/api/v1/protocol-categories", json={"label": "Biofilm inhibition"})
    r = await client.post("/api/v1/protocol-categories", json={"label": "biofilm INHIBITION"})
    assert r.status_code == 409


async def test_bad_pattern_is_422(client):
    created = (
        await client.post("/api/v1/protocol-categories", json={"label": "Biofilm inhibition"})
    ).json()
    r = await client.patch(
        f"/api/v1/protocol-categories/{created['id']}", json={"name_pattern": "{species} biofilm"}
    )
    assert r.status_code == 422


async def test_category_in_use_cannot_be_deleted(client):
    cats = (await client.post("/api/v1/protocol-categories/defaults")).json()
    cyto = next(c for c in cats if c["label"] == "Cytotoxicity")
    hepg2 = {
        "term_id": "http://purl.obolibrary.org/obo/CLO_0003703",
        "label": "HepG2 cell",
        "ontology_source": "CLO",
    }
    body = {
        "protocol_type": "cell_based",
        "category": "Cytotoxicity",
        "readout_definitions": [{"name": "Signal", "data_type": "numeric"}],
        "ontology_annotations": {"cell_line": [hepg2]},
    }
    assert (await client.post("/api/v1/protocols", json=body)).status_code == 201
    r = await client.delete(f"/api/v1/protocol-categories/{cyto['id']}")
    assert r.status_code == 409


async def test_editor_cannot_create_but_viewer_can_list(editor_client, viewer_client):
    r = await editor_client.post(
        "/api/v1/protocol-categories", json={"label": "Biofilm inhibition"}
    )
    assert r.status_code == 403
    assert (await viewer_client.get("/api/v1/protocol-categories")).status_code == 200
