"""Setup checklist: what an admin still has to configure, reported as counts and flags."""

import pytest

from cellar.domain.shared.protocol_naming import DEFAULT_CATEGORY_PATTERNS

URL = "/api/v1/workspace-setup"


@pytest.fixture(autouse=True)
def _no_env_key(monkeypatch):
    monkeypatch.delenv("BIOPORTAL_API_KEY", raising=False)


@pytest.fixture(autouse=True)
def _stored_secrets(api_app, monkeypatch):
    """The test container's provider reads env only; give it a store so saved keys resolve."""
    from cellar.domain.shared.secret_provider import SecretProvider

    store: dict[str, str] = {}
    provider = api_app.state.container[SecretProvider]

    async def get_secret(key):
        return store.get(key)

    async def set_secret(key, value):
        store[key] = value

    monkeypatch.setattr(provider, "get_secret", get_secret)
    monkeypatch.setattr(provider, "set_secret", set_secret)


async def test_fresh_workspace_reports_everything_missing(client):
    r = await client.get(URL)
    assert r.status_code == 200, r.text
    assert r.json() == {
        "missing_default_categories": list(DEFAULT_CATEGORY_PATTERNS),
        "missing_default_forms": 0,  # forms hang off categories the workspace has; it has none
        "bioportal_key": False,
        "home_organisms": 0,
        "targets": 0,
    }


async def test_a_deleted_shipped_form_counts_as_missing(client):
    await client.post("/api/v1/protocol-categories/defaults")
    forms = (await client.get("/api/v1/protocol-forms")).json()
    mbc = next(f for f in forms if f["name"] == "MBC")
    await client.delete(f"/api/v1/protocol-forms/{mbc['id']}")
    body = (await client.get(URL)).json()
    assert body["missing_default_categories"] == []
    assert body["missing_default_forms"] == 1


async def test_after_seeding_a_key_a_home_organism_and_a_target_it_is_done(client, make_target):
    await client.post("/api/v1/protocol-categories/defaults")
    key = await client.post(
        "/api/v1/api-keys",
        json={"key_name": "bioportal", "label": "BioPortal", "secret_value": "s3cret-value"},
    )
    assert key.status_code == 201, key.text
    org = {"term_id": "NCBITAXON:1773", "label": "Mycobacterium tuberculosis"}
    human = {"term_id": "NCBITAXON:9606", "label": "Homo sapiens"}
    r = await client.put("/api/v1/settings/home-organism", json={"terms": [org, human]})
    assert r.status_code == 200, r.text
    await make_target("InhA")
    resp = await client.get(URL)
    assert resp.json() == {
        "missing_default_categories": [],
        "missing_default_forms": 0,
        "bioportal_key": True,
        "home_organisms": 2,
        "targets": 1,
    }
    assert "s3cret-value" not in resp.text


async def test_an_env_configured_key_counts_without_a_workspace_key(client, monkeypatch):
    monkeypatch.setenv("BIOPORTAL_API_KEY", "env-secret-value")
    resp = await client.get(URL)
    assert resp.json()["bioportal_key"] is True
    assert "env-secret-value" not in resp.text


async def test_only_admins_may_read_it(editor_client, viewer_client):
    assert (await editor_client.get(URL)).status_code == 403
    assert (await viewer_client.get(URL)).status_code == 403
