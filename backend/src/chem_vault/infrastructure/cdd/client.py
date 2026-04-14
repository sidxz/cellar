"""CDD Vault REST API client — reusable HTTP adapter.

Returns raw dicts (parsed JSON). Domain mapping happens in the application layer.
Designed for reuse across protocol, run, molecule, plate, project imports.

CDD molecule export is async:
  1. POST /molecules/query  (JSON body with "async": true) → {id, status: "new"}
  2. GET  /exports/{id}     → {status: "started"} (poll)
  3. GET  /exports/{id}     → 302 redirect to result (follow it)
  4. Result JSON            → {count, objects: [{smiles, ...}]}
"""

from __future__ import annotations

from typing import Any

import httpx

from chem_vault.application.cdd_import.errors import (
    CddAuthError,
    CddClientError,
    CddConnectionError,
    CddNotFoundError,
    CddRateLimitError,
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

    async def _get(self, url: str, api_key: str, *, follow_redirects: bool = False, timeout: float = 30.0) -> Any:
        try:
            response = await self._http.get(
                url, headers=self._headers(api_key),
                timeout=timeout, follow_redirects=follow_redirects,
            )
        except (httpx.ConnectError, httpx.TimeoutException) as exc:
            raise CddConnectionError(f"Cannot reach CDD Vault: {exc}") from exc
        self._check_response(response)
        return response.json()

    async def _post_query(self, url: str, api_key: str, body: dict[str, Any], *, timeout: float = 30.0) -> Any:
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

    async def get_protocol(
        self, vault_id: str, api_key: str, protocol_id: int
    ) -> dict[str, Any]:
        """Fetch a single protocol by CDD ID."""
        return await self._get(
            f"{BASE_URL}/vaults/{vault_id}/protocols/{protocol_id}", api_key
        )

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
            all_ids, _ = await self.list_molecule_ids(
                vault_id, api_key, page_size=max_molecules,
            )
            ids_to_export = all_ids[:max_molecules]
            body["molecules"] = ",".join(str(i) for i in ids_to_export)

        return await self.start_export(vault_id, api_key, "molecules", body=body)

    async def list_molecule_ids(
        self,
        vault_id: str,
        api_key: str,
        *,
        offset: int = 0,
        page_size: int = 1000,
    ) -> tuple[list[int], int]:
        """Fetch molecule IDs using only_ids=true (sync, fast, no structures).

        Returns (list_of_cdd_ids, total_count).
        """
        url = (
            f"{BASE_URL}/vaults/{vault_id}/molecules"
            f"?only_ids=true&page_size={page_size}&offset={offset}"
        )
        data = await self._get(url, api_key)
        if isinstance(data, list):
            return data, len(data)
        raw_objects = data.get("objects", [])
        ids = [obj if isinstance(obj, int) else obj["id"] for obj in raw_objects]
        total = data.get("count", len(ids))
        return ids, total

    async def check_export_progress(
        self, vault_id: str, api_key: str, export_id: int
    ) -> str:
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

        Follows the 302 redirect to the presigned S3 URL and writes the
        response body in chunks — never holds the full payload in memory.
        """
        url = f"{BASE_URL}/vaults/{vault_id}/exports/{export_id}"
        try:
            response = await self._http.get(
                url, headers=self._headers(api_key),
                timeout=120.0, follow_redirects=False,
            )
        except (httpx.ConnectError, httpx.TimeoutException) as exc:
            raise CddConnectionError(f"Cannot reach CDD Vault: {exc}") from exc

        if response.status_code != 302:
            raise CddClientError(
                f"Expected 302 redirect for finished export, got {response.status_code}",
                status_code=response.status_code,
            )

        redirect_url = response.headers["location"]
        # Presigned S3 URL — do NOT send CDD auth header, stream to disk
        try:
            async with self._http.stream(
                "GET", redirect_url, timeout=1800.0, follow_redirects=True,
            ) as stream:
                if not stream.is_success:
                    raise CddClientError(
                        f"Export download failed: {stream.status_code}",
                        status_code=stream.status_code,
                    )
                with open(dest_path, "wb") as f:
                    async for chunk in stream.aiter_bytes(chunk_size=65536):
                        f.write(chunk)
        except (httpx.ConnectError, httpx.TimeoutException) as exc:
            raise CddConnectionError(f"Export download timed out: {exc}") from exc

    async def get_export_status(
        self, vault_id: str, api_key: str, export_id: int
    ) -> dict[str, Any]:
        """Check status of an async export (legacy — loads entire response into memory).

        Prefer check_export_progress + stream_export_to_file for large exports.

        Returns:
            - ``{"status": "new"|"started", ...}`` while processing
            - ``{"count": N, "objects": [...]}`` when finished (after following 302 redirect)

        CDD may return 403 while the export is queued/processing; this is
        treated as "not ready yet" rather than an auth error.
        """
        url = f"{BASE_URL}/vaults/{vault_id}/exports/{export_id}"
        try:
            response = await self._http.get(
                url, headers=self._headers(api_key),
                timeout=120.0, follow_redirects=False,
            )
        except (httpx.ConnectError, httpx.TimeoutException) as exc:
            raise CddConnectionError(f"Cannot reach CDD Vault: {exc}") from exc

        # 302 = export finished, redirect to presigned result URL
        if response.status_code == 302:
            redirect_url = response.headers["location"]
            # Presigned URL — do NOT send CDD auth header
            try:
                redirect_resp = await self._http.get(
                    redirect_url, timeout=300.0, follow_redirects=True,
                )
            except (httpx.ConnectError, httpx.TimeoutException) as exc:
                raise CddConnectionError(f"Cannot fetch export result: {exc}") from exc
            if not redirect_resp.is_success:
                raise CddClientError(
                    f"Export result fetch failed: {redirect_resp.status_code}",
                    status_code=redirect_resp.status_code,
                )
            return redirect_resp.json()

        # CDD returns 403 with a valid JSON body ({"status":"started"}) for
        # queued/in-progress exports. If the body isn't valid JSON, treat it
        # as a real auth error rather than silently swallowing the failure.
        if response.status_code == 403:
            try:
                return response.json()
            except (ValueError, KeyError):
                raise CddAuthError(
                    "CDD Vault returned 403 with no valid JSON body",
                    status_code=403,
                )

        if response.status_code == 401:
            raise CddAuthError(
                "CDD Vault API key is invalid or expired",
                status_code=response.status_code,
            )

        if not response.is_success:
            raise CddClientError(
                f"CDD Vault API returned {response.status_code}",
                status_code=response.status_code,
            )

        return response.json()

    async def get_molecule_count(
        self, vault_id: str, api_key: str
    ) -> int:
        """Get total molecule count via a sync metadata-only call."""
        url = f"{BASE_URL}/vaults/{vault_id}/molecules?page_size=1&offset=0"
        data = await self._get(url, api_key)
        return data.get("count", 0) if isinstance(data, dict) else 0
