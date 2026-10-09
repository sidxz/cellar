"""Port: where the target catalog comes from (prot-cellar).

The application layer only knows "give me every target for the caller" and
"create this target as the caller", always with the caller's own credentials.
The adapter lives in ``infrastructure/prot_cellar`` and must raise
``AuthorizationError`` when the source refuses the forwarded credentials and
``ServiceUnavailableError`` when it cannot be reached — both already map to
HTTP statuses in the API layer. ``create_target`` also raises ``NotFoundError``
(organism or protein not in the source), ``ConflictError`` and
``ValidationError`` (the source rejected the target, its message passed on).
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


@dataclass(frozen=True, kw_only=True)
class NewTarget:
    """A target to create in the source. Input is already validated by the use case."""

    name: str
    target_type: str
    organism_tax_id: int
    organism_label: str
    """Only for messages ("Homo sapiens is not in ProtCellar")."""
    chembl_id: str | None = None
    protein_identifier: str | None = None
    """UniProt accession or entry name; set only for single-protein and domain targets."""


@runtime_checkable
class TargetSource(Protocol):
    async def fetch_all(self, *, forwarded_headers: Mapping[str, str]) -> list[SourceTarget]:
        """Every target visible to the caller. Pages internally; no cap."""
        ...

    async def create_target(
        self, request: NewTarget, *, forwarded_headers: Mapping[str, str]
    ) -> SourceTarget:
        """Create the target as the caller and return it as the mirror needs it."""
        ...
