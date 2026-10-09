"""HTTP adapter for the ``TargetSource`` port — prot-cellar's ``/api/v1/targets``.

Auth: forwards the caller's own Duar headers (``Authorization`` +
``X-Authz-Token``). Both apps are members of the same Duar realm, so a
chem-vault2-minted authz token is accepted by prot-cellar as-is. The service
key is never sent.

Paging: keyset cursor, ``limit=200`` (prot-cellar's max), until
``next_cursor`` is null — the whole catalog, no cap.

Create (``create_target``): resolve the organism by NCBI tax id and, for a
protein target, the protein by UniProt accession or entry name, then
``POST /api/v1/targets`` as the caller. Refusals become the port's
DomainErrors, never raw HTTP errors.

Organism names are not on prot-cellar's target DTO; they are resolved via
``GET /api/v1/organisms/{id}`` with a per-call cache (a workspace typically
has 1-3 distinct organisms).
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from urllib.parse import quote

import httpx
import structlog

from cellar.application.screening.target_source import NewTarget, SourceTarget, TargetSource
from cellar.domain.screening_assay.enums import TargetType
from cellar.domain.shared.errors import (
    AuthorizationError,
    ConflictError,
    NotFoundError,
    ServiceUnavailableError,
    ValidationError,
)
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

    async def create_target(
        self, request: NewTarget, *, forwarded_headers: Mapping[str, str]
    ) -> SourceTarget:
        """Resolve the organism (and protein), then ``POST /api/v1/targets`` as the caller."""
        headers = dict(forwarded_headers)
        organism = await self._write_step(
            "GET",
            f"/api/v1/organisms/resolve/{request.organism_tax_id}",
            headers,
            not_found=NotFoundError(
                "Organism",
                str(request.organism_tax_id),
                message=f"{request.organism_label} (NCBITaxon {request.organism_tax_id}) "
                "is not in ProtCellar. Add the organism there first.",
            ),
        )
        components: list[dict[str, str]] = []
        if request.protein_identifier:
            protein = await self._write_step(
                "GET",
                f"/api/v1/proteins/resolve/{quote(request.protein_identifier, safe='')}",
                headers,
                not_found=NotFoundError(
                    "Protein",
                    request.protein_identifier,
                    message=f"Protein {request.protein_identifier} is not in ProtCellar",
                ),
            )
            components = [{"protein_id": protein["id"], "relationship": "single_protein"}]
        created = await self._write_step(
            "POST",
            "/api/v1/targets",
            headers,
            json={
                "pref_name": request.name,
                "target_type": request.target_type,
                "organism_id": organism["id"],
                "chembl_id": request.chembl_id,
                "components": components,
            },
        )
        try:
            ttype = created["target_type"]
            return SourceTarget(
                id=uuid.UUID(created["id"]),
                name=created["pref_name"],
                target_type=ttype if ttype in _KNOWN_TYPES else TargetType.UNKNOWN.value,
                organism=organism.get("scientific_name"),
                chembl_id=created.get("chembl_id"),
                version=int(created["version"]),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ServiceUnavailableError(
                "prot-cellar created the target but returned an unusable response; "
                "it appears after the next sync",
                detail=repr(exc)[:200],
            ) from exc

    async def _write_step(
        self,
        method: str,
        path: str,
        headers: dict[str, str],
        *,
        json: dict | None = None,
        not_found: NotFoundError | None = None,
    ) -> dict:
        """One call of the create flow; each refusal becomes the DomainError the port names."""
        resp = await self._send(method, path, headers, json=json)
        if resp.status_code in (401, 403):
            raise AuthorizationError(
                "You need editor access in ProtCellar",
                detail=f"({resp.status_code}) {_detail(resp)}",
            )
        if resp.status_code == 404 and not_found is not None:
            raise not_found
        if resp.status_code == 409:
            raise ConflictError(_message(resp), detail=_detail(resp))
        if resp.status_code in (410, 422):
            raise ValidationError(_message(resp), detail=_detail(resp))
        return self._json(resp, path)

    async def _get_json(
        self, path: str, headers: dict[str, str], params: dict[str, str | int]
    ) -> dict:
        resp = await self._send("GET", path, headers, params=params)
        if resp.status_code in (401, 403):
            detail = _detail(resp)
            raise AuthorizationError(
                "prot-cellar refused the request: editor role required",
                detail=(
                    f"({resp.status_code}) {detail}. "
                    "Target reads in prot-cellar require the editor role."
                ),
            )
        return self._json(resp, path)

    async def _send(
        self,
        method: str,
        path: str,
        headers: dict[str, str],
        *,
        params: dict[str, str | int] | None = None,
        json: dict | None = None,
    ) -> httpx.Response:
        try:
            return await self._client.request(
                method,
                f"{self._base}{path}",
                headers=headers,
                params=params,
                json=json,
                timeout=self._timeout,
            )
        except httpx.HTTPError as exc:
            raise ServiceUnavailableError(f"prot-cellar unreachable: {exc}") from exc

    @staticmethod
    def _json(resp: httpx.Response, path: str) -> dict:
        if not resp.is_success:
            detail = _detail(resp)
            raise ServiceUnavailableError(
                f"prot-cellar returned {resp.status_code} for {path}",
                detail=f"({resp.status_code}) {detail}",
            )
        try:
            return resp.json()
        except ValueError as exc:
            raise ServiceUnavailableError(
                f"prot-cellar returned non-JSON for {path}",
                detail=resp.text[:200],
            ) from exc


def _detail(resp: httpx.Response) -> str:
    try:
        body = resp.json()
    except ValueError:
        return resp.text[:200]
    return str(body.get("detail") or body.get("message") or body)[:200]


def _message(resp: httpx.Response) -> str:
    """prot-cellar's own error message when it sent a plain one, else a generic sentence."""
    try:
        body = resp.json()
    except ValueError:
        body = None
    if isinstance(body, dict):
        for key in ("message", "detail"):
            if isinstance(body.get(key), str) and body[key].strip():
                return body[key].strip()[:200]
    return f"ProtCellar rejected the target ({resp.status_code})"
