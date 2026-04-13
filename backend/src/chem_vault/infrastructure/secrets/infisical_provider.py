"""Infisical REST API adapter for SecretProvider."""

from __future__ import annotations

import logging

import httpx

logger = logging.getLogger(__name__)


class InfisicalSecretProvider:
    """Stores and retrieves secrets via the Infisical REST API (v3).

    Uses machine-identity auth (Bearer token).  Secrets are stored in a
    single Infisical project/environment and keyed by
    ``{workspace_id}:{key_name}``.

    If Infisical is unreachable, ``get_secret`` returns ``None`` rather than
    raising — callers should treat missing secrets gracefully.
    """

    def __init__(
        self,
        *,
        base_url: str = "http://infisical:8080",
        token: str,
        project_id: str,
        environment: str = "dev",
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._project_id = project_id
        self._environment = environment
        self._headers = {
            "Authorization": f"Bearer {token}",
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
            async with httpx.AsyncClient() as client:
                resp = await client.get(url, headers=self._headers, timeout=10.0)
                if resp.status_code == 404:
                    return None
                resp.raise_for_status()
                data = resp.json()
                return data.get("secret", {}).get("secretValue")
        except Exception:
            logger.warning("Failed to retrieve secret %s from Infisical", key, exc_info=True)
            return None

    async def set_secret(self, key: str, value: str) -> None:
        safe_key = self._sanitize_key(key)
        # Try PATCH (update) first; if 404, fall back to POST (create).
        body = {
            "workspaceId": self._project_id,
            "environment": self._environment,
            "secretValue": value,
        }
        async with httpx.AsyncClient() as client:
            patch_url = f"{self._base_url}/api/v3/secrets/raw/{safe_key}"
            resp = await client.patch(
                patch_url, headers=self._headers, json=body, timeout=10.0,
            )
            if resp.status_code == 404:
                create_body = {
                    **body,
                    "secretName": safe_key,
                    "type": "shared",
                }
                post_url = f"{self._base_url}/api/v3/secrets/raw/{safe_key}"
                resp = await client.post(
                    post_url, headers=self._headers, json=create_body, timeout=10.0,
                )
            resp.raise_for_status()

    async def delete_secret(self, key: str) -> None:
        safe_key = self._sanitize_key(key)
        url = (
            f"{self._base_url}/api/v3/secrets/raw/{safe_key}"
            f"?workspaceId={self._project_id}"
            f"&environment={self._environment}"
        )
        async with httpx.AsyncClient() as client:
            resp = await client.delete(url, headers=self._headers, timeout=10.0)
            # 404 is acceptable — secret already gone.
            if resp.status_code != 404:
                resp.raise_for_status()
