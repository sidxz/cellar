"""Org directory — reads Duar's internal org list for pickers/labels.

Org *identity* arrives on every request via JWT claims; this service only
supplies the workspace-wide org list (names/slugs) for UI purposes.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass

import httpx


@dataclass(frozen=True)
class OrgSummary:
    id: uuid.UUID
    slug: str
    name: str
    is_public: bool


class OrgDirectory:
    # ponytail: per-process TTL cache; swap to Valkey if cross-process staleness ever matters
    def __init__(
        self,
        base_url: str,
        service_key: str,
        ttl_seconds: float = 300.0,
        transport: httpx.AsyncBaseTransport | None = None,
        include_disabled: bool = False,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._service_key = service_key
        self._ttl = ttl_seconds
        self._transport = transport
        self._include_disabled = include_disabled
        self._cached_at: float = float("-inf")
        self._cache: list[OrgSummary] = []

    async def list_orgs(self) -> list[OrgSummary]:
        if time.monotonic() - self._cached_at < self._ttl:
            return self._cache
        params = {"include_disabled": "true"} if self._include_disabled else None
        async with httpx.AsyncClient(transport=self._transport, timeout=10.0) as client:
            resp = await client.get(
                f"{self._base_url}/organizations",
                headers={"X-Service-Key": self._service_key},
                params=params,
            )
        resp.raise_for_status()
        self._cache = [
            OrgSummary(
                id=uuid.UUID(o["id"]),
                slug=o["slug"],
                name=o["name"],
                is_public=bool(o["is_public"]),
            )
            for o in resp.json()
        ]
        self._cached_at = time.monotonic()
        return self._cache
