"""Tests for CddVaultClient using respx to mock HTTP."""

import json

import httpx
import pytest
import respx

from cellar.application.cdd_import.errors import (
    CddAuthError,
    CddClientError,
    CddConnectionError,
    CddNotFoundError,
)
from cellar.infrastructure.cdd.client import CddVaultClient

VAULT_ID = "12345"
API_KEY = "test-api-key"


@pytest.fixture
def client() -> CddVaultClient:
    return CddVaultClient(http_client=httpx.AsyncClient())


@respx.mock
@pytest.mark.asyncio
async def test_list_protocols_returns_list(client: CddVaultClient):
    respx.get(
        f"https://app.collaborativedrug.com/api/v1/vaults/{VAULT_ID}/protocols"
    ).mock(
        return_value=httpx.Response(
            200,
            json={
                "count": 2,
                "offset": 0,
                "page_size": 50,
                "objects": [
                    {"id": 1, "name": "Kinase IC50", "class": "protocol"},
                    {"id": 2, "name": "Cell Viability", "class": "protocol"},
                ],
            },
        )
    )
    result = await client.list_protocols(VAULT_ID, API_KEY)
    assert len(result) == 2
    assert result[0]["name"] == "Kinase IC50"


@respx.mock
@pytest.mark.asyncio
async def test_list_protocols_sends_auth_header(client: CddVaultClient):
    route = respx.get(
        f"https://app.collaborativedrug.com/api/v1/vaults/{VAULT_ID}/protocols"
    ).mock(
        return_value=httpx.Response(200, json={"count": 0, "objects": []})
    )
    await client.list_protocols(VAULT_ID, API_KEY)
    assert route.calls[0].request.headers["X-CDD-Token"] == API_KEY


@respx.mock
@pytest.mark.asyncio
async def test_list_protocols_auth_error(client: CddVaultClient):
    respx.get(
        f"https://app.collaborativedrug.com/api/v1/vaults/{VAULT_ID}/protocols"
    ).mock(return_value=httpx.Response(401, json={"error": "Unauthorized"}))
    with pytest.raises(CddAuthError):
        await client.list_protocols(VAULT_ID, API_KEY)


@respx.mock
@pytest.mark.asyncio
async def test_list_protocols_not_found(client: CddVaultClient):
    respx.get(
        f"https://app.collaborativedrug.com/api/v1/vaults/{VAULT_ID}/protocols"
    ).mock(return_value=httpx.Response(404, json={"error": "Not Found"}))
    with pytest.raises(CddNotFoundError):
        await client.list_protocols(VAULT_ID, API_KEY)


@respx.mock
@pytest.mark.asyncio
async def test_get_protocol_returns_dict(client: CddVaultClient):
    respx.get(
        f"https://app.collaborativedrug.com/api/v1/vaults/{VAULT_ID}/protocols/1"
    ).mock(
        return_value=httpx.Response(
            200,
            json={
                "id": 1,
                "name": "Kinase IC50",
                "readout_definitions": [
                    {"id": 100, "name": "% Inhibition", "type": "Number", "unit": "%"}
                ],
            },
        )
    )
    result = await client.get_protocol(VAULT_ID, API_KEY, 1)
    assert result["name"] == "Kinase IC50"
    assert len(result["readout_definitions"]) == 1


@respx.mock
@pytest.mark.asyncio
async def test_get_protocol_not_found(client: CddVaultClient):
    respx.get(
        f"https://app.collaborativedrug.com/api/v1/vaults/{VAULT_ID}/protocols/999"
    ).mock(return_value=httpx.Response(404, json={"error": "Not Found"}))
    with pytest.raises(CddNotFoundError):
        await client.get_protocol(VAULT_ID, API_KEY, 999)


@respx.mock
@pytest.mark.asyncio
async def test_connection_error(client: CddVaultClient):
    respx.get(
        f"https://app.collaborativedrug.com/api/v1/vaults/{VAULT_ID}/protocols"
    ).mock(side_effect=httpx.ConnectError("Connection refused"))
    with pytest.raises(CddConnectionError):
        await client.list_protocols(VAULT_ID, API_KEY)


@respx.mock
@pytest.mark.asyncio
async def test_get_molecule_count_reads_count_from_post_query(client: CddVaultClient):
    route = respx.post(
        f"https://app.collaborativedrug.com/api/v1/vaults/{VAULT_ID}/molecules/query"
    ).mock(
        return_value=httpx.Response(
            200,
            json={"count": 502375, "offset": 0, "page_size": 1, "objects": [{"id": 7}]},
        )
    )
    assert await client.get_molecule_count(VAULT_ID, API_KEY) == 502375
    assert json.loads(route.calls[0].request.content) == {"page_size": 1}


@respx.mock
@pytest.mark.asyncio
async def test_list_molecule_ids_posts_only_ids_query(client: CddVaultClient):
    route = respx.post(
        f"https://app.collaborativedrug.com/api/v1/vaults/{VAULT_ID}/molecules/query"
    ).mock(return_value=httpx.Response(200, json={"count": 3, "objects": [11, 12, 13]}))
    assert await client.list_molecule_ids(VAULT_ID, API_KEY) == ([11, 12, 13], 3)
    assert json.loads(route.calls[0].request.content) == {"only_ids": True}


EXPORT_URL = f"https://app.collaborativedrug.com/api/v1/vaults/{VAULT_ID}/exports/77"
EXPORT_BODY = b'{"count": 1, "objects": [{"id": 5, "class": "plate"}]}'


@respx.mock
@pytest.mark.asyncio
async def test_stream_export_writes_file_served_directly(client: CddVaultClient, tmp_path):
    respx.get(EXPORT_URL).mock(return_value=httpx.Response(200, content=EXPORT_BODY))
    dest = tmp_path / "raw_export.json"
    await client.stream_export_to_file(VAULT_ID, API_KEY, 77, str(dest))
    assert dest.read_bytes() == EXPORT_BODY


@respx.mock
@pytest.mark.asyncio
async def test_stream_export_follows_redirect_without_vault_token(
    client: CddVaultClient, tmp_path
):
    s3_url = "https://exports.s3.amazonaws.com/77.json?X-Amz-Signature=abc"
    respx.get(EXPORT_URL).mock(return_value=httpx.Response(302, headers={"Location": s3_url}))
    s3 = respx.get(s3_url).mock(return_value=httpx.Response(200, content=EXPORT_BODY))
    dest = tmp_path / "raw_export.json"
    await client.stream_export_to_file(VAULT_ID, API_KEY, 77, str(dest))
    assert dest.read_bytes() == EXPORT_BODY
    assert "X-CDD-Token" not in s3.calls[0].request.headers


@respx.mock
@pytest.mark.asyncio
async def test_stream_export_not_ready_is_not_reported_as_bad_key(
    client: CddVaultClient, tmp_path
):
    respx.get(EXPORT_URL).mock(
        return_value=httpx.Response(403, json={"id": 77, "status": "started"})
    )
    dest = tmp_path / "raw_export.json"
    with pytest.raises(CddClientError) as exc_info:
        await client.stream_export_to_file(VAULT_ID, API_KEY, 77, str(dest))
    assert exc_info.value.status_code == 403
    assert not isinstance(exc_info.value, CddAuthError)
    assert not dest.exists()
