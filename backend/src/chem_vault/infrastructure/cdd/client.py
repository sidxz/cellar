"""CDD Vault REST API client — reusable HTTP adapter.

Returns raw dicts (parsed JSON). Domain mapping happens in the application layer.
Designed for reuse across protocol, run, molecule, plate, project imports.
"""

from __future__ import annotations

from typing import Any

import httpx

from chem_vault.application.cdd_import.errors import (
    CddAuthError,
    CddClientError,
    CddConnectionError,
    CddNotFoundError,
)

__all__ = ["CddVaultClient"]

BASE_URL = "https://app.collaborativedrug.com/api/v1"


class CddVaultClient:
    """HTTP adapter for the CDD Vault REST API.

    Stateless — vault_id and api_key passed per call.
    """

    def __init__(self, http_client: httpx.AsyncClient) -> None:
        self._http = http_client

    def _headers(self, api_key: str) -> dict[str, str]:
        return {"X-CDD-Token": api_key, "Accept": "application/json"}

    def _check_response(self, response: httpx.Response) -> None:
        if response.status_code in (401, 403):
            raise CddAuthError(
                "CDD API key is invalid or expired",
                status_code=response.status_code,
            )
        if response.status_code == 404:
            raise CddNotFoundError(
                "CDD resource not found",
                status_code=404,
            )
        if not response.is_success:
            raise CddClientError(
                f"CDD API returned {response.status_code}",
                status_code=response.status_code,
            )

    async def _get(self, url: str, api_key: str) -> Any:
        try:
            response = await self._http.get(url, headers=self._headers(api_key), timeout=30.0)
        except (httpx.ConnectError, httpx.TimeoutException) as exc:
            raise CddConnectionError(f"Cannot reach CDD Vault: {exc}") from exc
        self._check_response(response)
        return response.json()

    async def list_protocols(self, vault_id: str, api_key: str) -> list[dict[str, Any]]:
        """Fetch all protocols from a CDD Vault, handling pagination."""
        all_objects: list[dict[str, Any]] = []
        offset = 0
        page_size = 50
        while True:
            url = f"{BASE_URL}/vaults/{vault_id}/protocols?page_size={page_size}&offset={offset}"
            data = await self._get(url, api_key)
            objects = data.get("objects", [])
            all_objects.extend(objects)
            if len(objects) < page_size:
                break
            offset += page_size
        return all_objects

    async def get_protocol(
        self, vault_id: str, api_key: str, protocol_id: int
    ) -> dict[str, Any]:
        """Fetch a single protocol by CDD ID."""
        return await self._get(
            f"{BASE_URL}/vaults/{vault_id}/protocols/{protocol_id}", api_key
        )
