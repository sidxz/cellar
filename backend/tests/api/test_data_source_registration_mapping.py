"""API: registration mapping on a CDD data source and the vault-fields list."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine

from cellar.domain.shared.secret_provider import SecretProvider
from cellar.infrastructure.cdd.client import CddVaultClient
from tests.api.conftest import _create_test_app

DS = "/api/v1/data-sources"


class _Secrets:
    async def get_secret(self, ref: str) -> str | None:
        return "k"


@pytest.fixture
def cdd() -> AsyncMock:
    return AsyncMock(spec=CddVaultClient)


@pytest.fixture
async def client(database_url, _run_migrations, fake_auth, cdd):  # type: ignore[no-untyped-def]
    app = _create_test_app(
        database_url, fake_auth, overrides={CddVaultClient: cdd, SecretProvider: _Secrets()}
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:  # type: ignore[arg-type]
        yield ac
    await app.state.container[AsyncEngine].dispose()


async def _create(client: AsyncClient, name: str = "vault") -> dict:
    resp = await client.post(
        DS,
        json={
            "name": name,
            "source_type": "cdd_vault",
            "config": {"vault_id": "42"},
            "api_key_name": "cdd-key",
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def test_new_cdd_source_has_the_default_mapping(client: AsyncClient) -> None:
    ds = await _create(client)
    assert [c["header"] for c in ds["registration_mapping"]] == [
        "name|cdd_registry_number",
        "smiles|cxsmiles",
        "synonyms",
        "batch.molecule_batch_identifier",
        "batch.salt_name",
    ]
    em = {e["entity_type"]: e for e in ds["entity_mappings"]}
    assert em["molecule"]["field_mappings"] == [] and em["batch"]["field_mappings"] == []


async def test_patch_saves_a_valid_mapping(client: AsyncClient) -> None:
    ds = await _create(client)
    mapping = [
        {"header": "name", "target": "name"},
        {
            "header": "molecule_fields.Alternate Names",
            "target": "compound_id",
            "source": "Alternate Names",
            "separator": ";",
        },
    ]
    resp = await client.patch(f"{DS}/{ds['id']}", json={"registration_mapping": mapping})
    assert resp.status_code == 200, resp.text
    assert resp.json()["registration_mapping"][1]["separator"] == ";"
    again = (await client.get(f"{DS}/{ds['id']}")).json()
    assert again["registration_mapping"] == resp.json()["registration_mapping"]


async def test_patch_invalid_mapping_is_422_naming_the_field(client: AsyncClient) -> None:
    ds = await _create(client)
    bad = [
        {"header": "batch.batch_fields.LGCY Batch Name", "target": "compound_id", "source": "L"}
    ]
    resp = await client.patch(f"{DS}/{ds['id']}", json={"registration_mapping": bad})
    assert resp.status_code == 422, resp.text
    assert "batch.batch_fields.LGCY Batch Name" in resp.json()["message"]


async def test_viewer_cannot_patch_or_read_vault_fields(
    database_url,
    _run_migrations,
    workspace_id,
    user_id,
    client: AsyncClient,  # type: ignore[no-untyped-def]
) -> None:
    from tests.fakes.fake_auth import FakeAuth

    ds = await _create(client, "v2")
    viewer = FakeAuth(role="viewer", workspace_id=workspace_id, user_id=user_id)
    app = _create_test_app(database_url, viewer)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as vc:  # type: ignore[arg-type]
        patched = await vc.patch(f"{DS}/{ds['id']}", json={"registration_mapping": []})
        fields = await vc.get(f"{DS}/{ds['id']}/vault-fields")
    await app.state.container[AsyncEngine].dispose()
    assert patched.status_code == 403
    assert fields.status_code == 403


async def test_vault_fields_use_the_vault_response(client: AsyncClient, cdd: AsyncMock) -> None:
    ds = await _create(client)
    cdd.list_fields.return_value = {
        "molecule": [{"name": "Alternate Names"}],
        "batch": [{"name": "LGCY Batch Name"}],
    }
    resp = await client.get(f"{DS}/{ds['id']}/vault-fields")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert {"path": "molecule_fields.Alternate Names", "label": "Alternate Names"} in body[
        "molecule"
    ]
    assert {"path": "batch.batch_fields.LGCY Batch Name", "label": "LGCY Batch Name"} in body[
        "batch"
    ]
    assert {"path": "smiles|cxsmiles", "label": "SMILES"} in body["molecule"]
    cdd.list_fields.assert_awaited_once_with("42", "k")


async def test_vault_fields_fall_back_to_built_ins(client: AsyncClient, cdd: AsyncMock) -> None:
    ds = await _create(client)
    cdd.list_fields.return_value = {"unexpected": True}
    body = (await client.get(f"{DS}/{ds['id']}/vault-fields")).json()
    assert [f["path"] for f in body["batch"]][:2] == [
        "batch.name",
        "batch.molecule_batch_identifier",
    ]
    assert len(body["molecule"]) == 4
