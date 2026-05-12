"""Read-model protocol for enriched dose-response queries.

The concrete implementation lives in
``infrastructure.persistence.sqlalchemy.screening_assay.dose_response_enriched_reader``.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class MoleculeDisplayInfo:
    """Display metadata for a compound, sourced once per DR query.

    Carries everything a DR table row needs without forcing the client to
    page through ``/molecules`` to find structure / synonyms.
    """

    registration_number: str
    name: str
    smiles: str | None
    synonyms: list[str]


@runtime_checkable
class DoseResponseEnrichedReader(Protocol):
    """Application-layer protocol for enriched dose-response read-model queries."""

    async def resolve_molecules(
        self, molecule_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, MoleculeDisplayInfo]: ...

    async def resolve_batch_numbers(self, batch_ids: list[uuid.UUID]) -> dict[uuid.UUID, str]: ...
