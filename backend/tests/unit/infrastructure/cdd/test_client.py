"""Tests for CddVaultClient using respx to mock HTTP."""

import pytest
import httpx
import respx

from chem_vault.infrastructure.cdd.client import CddVaultClient
from chem_vault.application.cdd_import.errors import (
    CddAuthError,
    CddConnectionError,
    CddNotFoundError,
)

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
