"""Infisical REST API adapter for SecretProvider."""

from __future__ import annotations

from typing import Any

import httpx
import structlog

logger = structlog.get_logger(__name__)


class InfisicalSecretProvider:
    """Stores and retrieves secrets via the Infisical REST API (v3).

    Authenticates as a machine identity (Universal Auth): logs in with the
    client ID/secret on first use, and again whenever Infisical rejects the
    access token — those expire (30 days in dev).  Secrets are stored in a
    single Infisical project/environment and keyed by
    ``{workspace_id}:{key_name}``.

    If Infisical is unreachable, ``get_secret`` returns ``None`` rather than
    raising — callers should treat missing secrets gracefully.
    """

    def __init__(
        self,
        *,
        base_url: str = "http://infisical:8080",
        client_id: str,
        client_secret: str,
        project_id: str,
        environment: str = "dev",
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._client_id = client_id
        self._client_secret = client_secret
        self._project_id = project_id
        self._environment = environment
        self._token: str | None = None
        self._client = client or httpx.AsyncClient()

    async def _login(self) -> None:
        resp = await self._client.post(
            f"{self._base_url}/api/v1/auth/universal-auth/login",
            json={"clientId": self._client_id, "clientSecret": self._client_secret},
            timeout=10.0,
        )
        resp.raise_for_status()
        self._token = resp.json()["accessToken"]

    async def _send(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        """Send with the current token; log in again once if Infisical rejects it."""
        if self._token is None:
            await self._login()
        resp = await self._client.request(
            method, url, headers=self._headers(), timeout=10.0, **kwargs
        )
        if resp.status_code in (401, 403):
            await self._login()
            resp = await self._client.request(
                method, url, headers=self._headers(), timeout=10.0, **kwargs
            )
        return resp

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._token}",
            "Content-Type": "application/json",
        }

    @staticmethod
    def _sanitize_key(key: str) -> str:
        """Infisical secret names must be alphanumeric + underscores."""
        return key.replace(":", "_").replace("-", "_").upper()

    # ------------------------------------------------------------------
    # SecretProvider interface
    # ------------------------------------------------------------------

    async def get_secret(self, key: str) -> str | None:
        safe_key = self._sanitize_key(key)
        url = (
            f"{self._base_url}/api/v3/secrets/raw/{safe_key}"
            f"?workspaceId={self._project_id}"
            f"&environment={self._environment}"
        )
        try:
            resp = await self._send("GET", url)
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            data = resp.json()
            return data.get("secret", {}).get("secretValue")
        except Exception:
            # field name avoids the redaction denylist; this is the lookup key, not a secret value
            logger.warning("infisical.secret_retrieve_failed", key=key, exc_info=True)
            return None

    async def set_secret(self, key: str, value: str) -> None:
        safe_key = self._sanitize_key(key)
        # Try PATCH (update) first; if 404, fall back to POST (create).
        body = {
            "workspaceId": self._project_id,
            "environment": self._environment,
            "secretValue": value,
        }
        patch_url = f"{self._base_url}/api/v3/secrets/raw/{safe_key}"
        resp = await self._send("PATCH", patch_url, json=body)
        if resp.status_code == 404:
            create_body = {
                **body,
                "secretName": safe_key,
                "type": "shared",
            }
            post_url = f"{self._base_url}/api/v3/secrets/raw/{safe_key}"
            resp = await self._send("POST", post_url, json=create_body)
        resp.raise_for_status()

    async def delete_secret(self, key: str) -> None:
        safe_key = self._sanitize_key(key)
        url = (
            f"{self._base_url}/api/v3/secrets/raw/{safe_key}"
            f"?workspaceId={self._project_id}"
            f"&environment={self._environment}"
        )
        resp = await self._send("DELETE", url)
        # 404 is acceptable — secret already gone.
        if resp.status_code != 404:
            resp.raise_for_status()
