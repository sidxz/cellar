"""Read-model protocol for enriched readout data queries.

The concrete implementation lives in
``infrastructure.persistence.sqlalchemy.screening_assay.readout_data_enriched_reader``.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class MoleculeRegistrationRow:
    """Molecule id -> registration number mapping from the read model."""

    id: uuid.UUID
    registration_number: str


@dataclass(frozen=True)
class BatchNumberRow:
    """Batch id -> batch number mapping from the read model."""

    id: uuid.UUID
    batch_number: str


@dataclass(frozen=True)
class MoleculeDisplayRow:
    """Per-molecule display info: reg id, name, custom synonyms.

    Used to populate the readout-data table without forcing the client to
    page through ``/molecules`` (which only returns the first ~100, missing
    most compounds in larger screens).
    """

    registration_number: str
    name: str
    synonyms: list[str]


@runtime_checkable
class ReadoutDataEnrichedReader(Protocol):
    """Application-layer protocol for enriched readout data read-model queries."""

    async def resolve_molecule_registration_numbers(
        self, molecule_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, str]: ...

    async def resolve_molecules(
        self, molecule_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, MoleculeDisplayRow]: ...

    async def resolve_batch_numbers(self, batch_ids: list[uuid.UUID]) -> dict[uuid.UUID, str]: ...
