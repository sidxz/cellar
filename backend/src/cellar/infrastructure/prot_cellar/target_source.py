"""HTTP adapter for the ``TargetSource`` port — prot-cellar's ``/api/v1/targets``.

Auth: forwards the caller's own Duar headers (``Authorization`` +
``X-Authz-Token``). Both apps are members of the same Duar realm, so a
chem-vault2-minted authz token is accepted by prot-cellar as-is. The service
key is never sent.

Paging: keyset cursor, ``limit=200`` (prot-cellar's max), until
``next_cursor`` is null — the whole catalog, no cap.

Organism names are not on prot-cellar's target DTO; they are resolved via
``GET /api/v1/organisms/{id}`` with a per-call cache (a workspace typically
has 1-3 distinct organisms).
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping

import httpx
import structlog

from cellar.application.screening.target_source import SourceTarget, TargetSource
from cellar.domain.screening_assay.enums import TargetType
from cellar.domain.shared.errors import AuthorizationError, ServiceUnavailableError
from cellar.infrastructure.prot_cellar.settings import ProtCellarSettings

_log = structlog.get_logger(__name__)

PAGE_SIZE = 200
_KNOWN_TYPES = {t.value for t in TargetType}


class HttpTargetSource(TargetSource):
    def __init__(self, client: httpx.AsyncClient, settings: ProtCellarSettings) -> None:
        self._client = client
        self._base = settings.url.rstrip("/")
        self._timeout = settings.timeout_seconds

    async def fetch_all(self, *, forwarded_headers: Mapping[str, str]) -> list[SourceTarget]:
        headers = dict(forwarded_headers)
        organisms: dict[str, str | None] = {}
        out: list[SourceTarget] = []
        cursor: str | None = None
        while True:
            params: dict[str, str | int] = {"limit": PAGE_SIZE}
            if cursor:
                params["cursor"] = cursor
            page = await self._get_json("/api/v1/targets", headers, params)
            for item in page["items"]:
                org_id = item.get("organism_id")
                if org_id and org_id not in organisms:
                    organisms[org_id] = await self._organism_name(org_id, headers)
                ttype = item["target_type"]
                if ttype not in _KNOWN_TYPES:
                    _log.warning(
                        "targets.sync.unknown_type",
                        target_type=ttype,
                        target_id=item["id"],
                    )
                    ttype = TargetType.UNKNOWN.value
                out.append(
                    SourceTarget(
                        id=uuid.UUID(item["id"]),
                        name=item["pref_name"],
                        target_type=ttype,
                        organism=organisms.get(org_id) if org_id else None,
                        chembl_id=item.get("chembl_id"),
                        version=int(item["version"]),
                    )
                )
            cursor = page.get("next_cursor")
            if not cursor:
                return out

    async def _organism_name(self, org_id: str, headers: dict[str, str]) -> str | None:
        try:
            data = await self._get_json(f"/api/v1/organisms/{org_id}", headers, {})
        except (AuthorizationError, ServiceUnavailableError) as exc:
            _log.warning(
                "targets.sync.organism_lookup_failed",
                organism_id=org_id,
                reason=str(exc),
            )
            return None
        return data.get("scientific_name")

    async def _get_json(
        self, path: str, headers: dict[str, str], params: dict[str, str | int]
    ) -> dict:
        try:
            resp = await self._client.get(
                f"{self._base}{path}", headers=headers, params=params, timeout=self._timeout
            )
        except httpx.HTTPError as exc:
            raise ServiceUnavailableError(f"prot-cellar unreachable: {exc}") from exc
        if resp.status_code in (401, 403):
            detail = _detail(resp)
            raise AuthorizationError(
                f"prot-cellar refused the request ({resp.status_code}): {detail}. "
                "Target reads in prot-cellar require the editor role."
            )
        if resp.status_code >= 400:
            raise ServiceUnavailableError(
                f"prot-cellar returned {resp.status_code} for {path}: {_detail(resp)}"
            )
        return resp.json()


def _detail(resp: httpx.Response) -> str:
    try:
        body = resp.json()
    except ValueError:
        return resp.text[:200]
    return str(body.get("detail") or body.get("message") or body)[:200]
