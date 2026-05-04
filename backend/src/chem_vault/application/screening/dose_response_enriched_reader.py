"""Read-model protocol for enriched dose-response queries.

The concrete implementation lives in
``infrastructure.persistence.sqlalchemy.screening_assay.dose_response_enriched_reader``.
"""

from __future__ import annotations

import uuid
from typing import Protocol, runtime_checkable


@runtime_checkable
class DoseResponseEnrichedReader(Protocol):
    """Application-layer protocol for enriched dose-response read-model queries."""

    async def resolve_molecule_names(
        self, molecule_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, str]: ...

    async def resolve_batch_numbers(
        self, batch_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, str]: ...
