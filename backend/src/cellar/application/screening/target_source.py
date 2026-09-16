"""Port: where the target catalog comes from (prot-cellar).

The application layer only knows "give me every target for the caller, using
the caller's own credentials". The adapter lives in
``infrastructure/prot_cellar`` and must raise ``AuthorizationError`` when the
source refuses the forwarded credentials and ``ServiceUnavailableError`` when
it cannot be reached — both already map to HTTP statuses in the API layer.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class SourceTarget:
    """One target as the source describes it — already flattened for the mirror."""

    id: uuid.UUID
    name: str
    target_type: str
    organism: str | None
    chembl_id: str | None
    version: int


@runtime_checkable
class TargetSource(Protocol):
    async def fetch_all(self, *, forwarded_headers: Mapping[str, str]) -> list[SourceTarget]:
        """Every target visible to the caller. Pages internally; no cap."""
        ...
