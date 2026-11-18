"""CDD Vault REST API client — reusable HTTP adapter.

Returns raw dicts (parsed JSON). Domain mapping happens in the application layer.
Designed for reuse across protocol, run, molecule, plate, project imports.

CDD molecule export is async:
  1. POST /molecules/query  (JSON body with "async": true) → {id, status: "new"}
  2. GET  /export_progress/{id} → {status: "started"} (poll)
  3. GET  /exports/{id}     → the file itself (200) or a 302 redirect to it
  4. Result JSON            → {count, objects: [{smiles, ...}]}
"""

from __future__ import annotations

from typing import Any

import httpx

from cellar.application.cdd_import.errors import (
    CddAuthError,
    CddClientError,
    CddConnectionError,
    CddNotFoundError,
    CddRateLimitError,
)

__all__ = ["CddVaultClient"]

BASE_URL = "https://app.collaborativedrug.com/api/v1"

# The vault returns at most 1000 records per synchronous page.
_MAX_PAGE_SIZE = 1000
# Names per lookup query: half a page, so a group normally comes back in one page.
_NAMES_PER_QUERY = 500


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
                "CDD Vault API key is invalid or expired",
                status_code=response.status_code,
            )
        if response.status_code == 404:
            raise CddNotFoundError(
                "CDD Vault resource not found",
                status_code=404,
            )
        if response.status_code == 429:
            retry_after = int(response.headers.get("Retry-After", "60"))
            raise CddRateLimitError(
                "CDD Vault API rate limit exceeded",
                retry_after=retry_after,
            )
        if not response.is_success:
            raise CddClientError(
                f"CDD Vault API returned {response.status_code}",
                status_code=response.status_code,
            )

    async def _get(
        self, url: str, api_key: str, *, follow_redirects: bool = False, timeout: float = 30.0
    ) -> Any:
        try:
            response = await self._http.get(
                url,
                headers=self._headers(api_key),
                timeout=timeout,
                follow_redirects=follow_redirects,
            )
        except (httpx.ConnectError, httpx.TimeoutException) as exc:
            raise CddConnectionError(f"Cannot reach CDD Vault: {exc}") from exc
        self._check_response(response)
        return response.json()

    async def _post_query(
        self, url: str, api_key: str, body: dict[str, Any], *, timeout: float = 30.0
    ) -> Any:
        """POST JSON body to a CDD /query endpoint."""
        try:
            response = await self._http.post(
                url,
                headers=self._headers(api_key),
                json=body,
                timeout=timeout,
            )
        except (httpx.ConnectError, httpx.TimeoutException) as exc:
            raise CddConnectionError(f"Cannot reach CDD Vault: {exc}") from exc
        self._check_response(response)
        return response.json()

    async def list_fields(self, vault_id: str, api_key: str) -> dict[str, Any]:
        """Field definitions of the vault (GET /vaults/{id}/fields), grouped by entity."""
        return await self._get(f"{BASE_URL}/vaults/{vault_id}/fields", api_key)

    async def list_protocols(self, vault_id: str, api_key: str) -> list[dict[str, Any]]:
        """Fetch all protocols from CDD Vault, handling pagination."""
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

    async def get_protocol(self, vault_id: str, api_key: str, protocol_id: int) -> dict[str, Any]:
        """Fetch a single protocol by CDD ID."""
        return await self._get(f"{BASE_URL}/vaults/{vault_id}/protocols/{protocol_id}", api_key)

    # ------------------------------------------------------------------
    # Generic async export (reusable across molecules, protocols, plates)
    # ------------------------------------------------------------------

    async def start_export(
        self,
        vault_id: str,
        api_key: str,
        entity_path: str,
        *,
        body: dict[str, Any] | None = None,
    ) -> int:
        """Trigger an async export via POST /vaults/{vault_id}/{entity_path}/query.

        Args:
            entity_path: CDD entity type path segment — "molecules", "protocols", etc.
            body: Additional query parameters (merged with {"async": true}).

        Returns the export job ID.
        """
        url = f"{BASE_URL}/vaults/{vault_id}/{entity_path}/query"
        payload: dict[str, Any] = {"async": True}
        if body:
            payload.update(body)
        data = await self._post_query(url, api_key, payload)
        return data["id"]

    # ------------------------------------------------------------------
    # Molecule async export
    # ------------------------------------------------------------------

    async def start_molecule_export(
        self,
        vault_id: str,
        api_key: str,
        *,
        molecule_ids: list[int] | None = None,
        modified_after: str | None = None,
        max_molecules: int | None = None,
    ) -> int:
        """Trigger an async molecule export via POST /molecules/query.

        Args:
            molecule_ids: Export only these CDD molecule IDs.
                          Cannot be combined with modified_after.
            modified_after: ISO 8601 timestamp — export molecules
                           modified/created after this date.
                           Cannot be combined with molecule_ids.
            max_molecules: Fetch this many IDs first (via only_ids),
                           then export them. Used for testing caps.

        Returns the export job ID.
        """
        if molecule_ids is not None and modified_after is not None:
            raise ValueError("molecule_ids and modified_after are mutually exclusive")

        body: dict[str, Any] = {}

        if molecule_ids is not None:
            body["molecules"] = ",".join(str(i) for i in molecule_ids)
        elif modified_after is not None:
            body["modified_after"] = modified_after
        elif max_molecules is not None:
            all_ids, _ = await self.list_molecule_ids(vault_id, api_key)
            ids_to_export = all_ids[:max_molecules]
            body["molecules"] = ",".join(str(i) for i in ids_to_export)

        return await self.start_export(vault_id, api_key, "molecules", body=body)

    async def list_molecule_ids(self, vault_id: str, api_key: str) -> tuple[list[int], int]:
        """Fetch every molecule ID using only_ids (sync, fast, no structures).

        The vault ignores page_size/offset for only_ids and returns all IDs.
        Returns (list_of_cdd_ids, total_count).
        """
        url = f"{BASE_URL}/vaults/{vault_id}/molecules/query"
        data = await self._post_query(url, api_key, {"only_ids": True})
        if isinstance(data, list):
            return data, len(data)
        raw_objects = data.get("objects", [])
        ids = [obj if isinstance(obj, int) else obj["id"] for obj in raw_objects]
        total = data.get("count", len(ids))
        return ids, total

    async def find_molecules_by_names(
        self, vault_id: str, api_key: str, names: list[str]
    ) -> list[dict[str, Any]]:
        """Molecules whose name or a synonym the vault matches to one of ``names``.

        Synchronous lookup without structures or batch details. The names go out in
        groups of ``_NAMES_PER_QUERY``; each group is paged until the vault's ``count``
        is reached, so a group matching more than one page of molecules is not cut short.
        """
        url = f"{BASE_URL}/vaults/{vault_id}/molecules/query"
        molecules: list[dict[str, Any]] = []
        for start in range(0, len(names), _NAMES_PER_QUERY):
            query = {
                "names": names[start : start + _NAMES_PER_QUERY],
                "no_structures": True,
                "only_batch_ids": True,
                "page_size": _MAX_PAGE_SIZE,
            }
            offset = 0
            while True:
                data = await self._post_query(url, api_key, {**query, "offset": offset})
                page = data.get("objects", [])
                molecules.extend(page)
                offset += len(page)
                if not page or offset >= data.get("count", 0):
                    break
        return molecules

    async def sample_molecules(
        self, vault_id: str, api_key: str, molecule_ids: list[int] | None, limit: int
    ) -> list[dict[str, Any]]:
        """One synchronous page of up to ``limit`` molecules with structures and batches.

        ``molecule_ids`` picks the molecules; None takes the vault's first ``limit``.
        """
        url = f"{BASE_URL}/vaults/{vault_id}/molecules/query"
        body: dict[str, Any] = {"page_size": limit}
        if molecule_ids is not None:
            body["molecules"] = ",".join(str(i) for i in molecule_ids)
        data = await self._post_query(url, api_key, body)
        return list(data.get("objects", []))[:limit]

    async def check_export_progress(self, vault_id: str, api_key: str, export_id: int) -> str:
        """Lightweight export status check via /export_progress (no data download).

        Returns status string: "new", "started", "finished", or "canceled".
        """
        url = f"{BASE_URL}/vaults/{vault_id}/export_progress/{export_id}"
        data = await self._get(url, api_key)
        return data.get("status", "unknown")

    async def stream_export_to_file(
        self, vault_id: str, api_key: str, export_id: int, dest_path: str
    ) -> None:
        """Download a finished export result by streaming to disk.

        The vault serves the file directly (200) or redirects (302) to a
        presigned S3 URL. Either way the body is written in chunks — never
        held fully in memory.
        """
        url = f"{BASE_URL}/vaults/{vault_id}/exports/{export_id}"
        try:
            async with self._http.stream(
                "GET",
                url,
                headers=self._headers(api_key),
                timeout=120.0,
                follow_redirects=False,
            ) as response:
                if not response.has_redirect_location:
                    await _write_body(response, dest_path)
                    return
                redirect_url = response.headers["location"]
            # Presigned S3 URL — do NOT send CDD auth header
            async with self._http.stream(
                "GET",
                redirect_url,
                timeout=1800.0,
                follow_redirects=True,
            ) as response:
                await _write_body(response, dest_path)
        except (httpx.ConnectError, httpx.TimeoutException) as exc:
            raise CddConnectionError(f"Cannot download CDD export: {exc}") from exc

    async def get_molecule_count(self, vault_id: str, api_key: str) -> int:
        """Get total molecule count via a one-row sync query."""
        url = f"{BASE_URL}/vaults/{vault_id}/molecules/query"
        data = await self._post_query(url, api_key, {"page_size": 1})
        return data.get("count", 0) if isinstance(data, dict) else 0

    async def get_plate_count(self, vault_id: str, api_key: str) -> int:
        """Get total plate count via a sync metadata-only call."""
        url = f"{BASE_URL}/vaults/{vault_id}/plates?page_size=1&offset=0"
        data = await self._get(url, api_key)
        return data.get("count", 0) if isinstance(data, dict) else 0


async def _write_body(response: httpx.Response, dest_path: str) -> None:
    """Stream a successful download response to ``dest_path``."""
    if not response.is_success:
        raise CddClientError(
            f"Export download failed: {response.status_code}",
            status_code=response.status_code,
        )
    with open(dest_path, "wb") as f:
        async for chunk in response.aiter_bytes(chunk_size=65536):
            f.write(chunk)
