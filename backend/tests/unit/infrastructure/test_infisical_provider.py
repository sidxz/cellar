"""Infisical secret store: log in as the machine identity, renew a rejected token."""

import json

import httpx
import respx

from cellar.infrastructure.di._core import _build_secret_provider
from cellar.infrastructure.secrets.infisical_provider import InfisicalSecretProvider

BASE = "http://infisical.test"
LOGIN = f"{BASE}/api/v1/auth/universal-auth/login"
SECRET = f"{BASE}/api/v3/secrets/raw/WS_1_CDD_VAULT"


def _token(value: str) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "accessToken": value,
            "expiresIn": 2592000,
            "accessTokenMaxTTL": 2592000,
            "tokenType": "Bearer",
        },
    )


def _secret(value: str) -> httpx.Response:
    return httpx.Response(
        200, json={"secret": {"secretKey": "WS_1_CDD_VAULT", "secretValue": value}}
    )


def _provider() -> InfisicalSecretProvider:
    return InfisicalSecretProvider(
        base_url=BASE, client_id="cid", client_secret="csecret", project_id="proj"
    )


@respx.mock
async def test_first_read_logs_in_with_client_credentials():
    login = respx.post(LOGIN).mock(return_value=_token("tok-1"))
    read = respx.get(SECRET).mock(return_value=_secret("vault-key"))

    assert await _provider().get_secret("ws-1:cdd_vault") == "vault-key"
    assert json.loads(login.calls[0].request.content) == {
        "clientId": "cid",
        "clientSecret": "csecret",
    }
    assert read.calls[0].request.headers["Authorization"] == "Bearer tok-1"


@respx.mock
async def test_expired_token_is_renewed_and_the_read_retried():
    login = respx.post(LOGIN).mock(side_effect=[_token("tok-old"), _token("tok-new")])

    def by_token(request: httpx.Request) -> httpx.Response:
        if request.headers["Authorization"] == "Bearer tok-new":
            return _secret("vault-key")
        # What Infisical answers once a 30-day access token has lapsed
        return httpx.Response(403, json={"message": "Token expired"})

    respx.get(SECRET).mock(side_effect=by_token)

    assert await _provider().get_secret("ws-1:cdd_vault") == "vault-key"
    assert login.call_count == 2


@respx.mock
async def test_rejected_login_reads_as_missing_secret():
    respx.post(LOGIN).mock(return_value=httpx.Response(401, json={"message": "Invalid"}))
    assert await _provider().get_secret("ws-1:cdd_vault") is None


@respx.mock
async def test_set_secret_creates_a_missing_secret_on_one_login():
    login = respx.post(LOGIN).mock(return_value=_token("tok-1"))
    update = respx.patch(SECRET).mock(return_value=httpx.Response(404))
    create = respx.post(SECRET).mock(return_value=httpx.Response(200, json={}))

    await _provider().set_secret("ws-1:cdd_vault", "vault-key")

    assert login.call_count == 1
    assert update.calls[0].request.headers["Authorization"] == "Bearer tok-1"
    assert json.loads(create.calls[0].request.content)["secretValue"] == "vault-key"


@respx.mock
async def test_secret_store_is_built_from_client_credentials(monkeypatch):
    monkeypatch.delenv("INFISICAL_TOKEN", raising=False)
    monkeypatch.setenv("INFISICAL_BASE_URL", BASE)
    monkeypatch.setenv("INFISICAL_CLIENT_ID", "cid")
    monkeypatch.setenv("INFISICAL_CLIENT_SECRET", "csecret")
    monkeypatch.setenv("INFISICAL_PROJECT_ID", "proj")
    respx.post(LOGIN).mock(return_value=_token("tok-1"))
    respx.get(SECRET).mock(return_value=_secret("vault-key"))

    assert await _build_secret_provider().get_secret("ws-1:cdd_vault") == "vault-key"
