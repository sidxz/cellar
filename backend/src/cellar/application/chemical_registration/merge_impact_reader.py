"""Read-model protocol for merge impact queries.

The concrete implementation lives in
``infrastructure.persistence.sqlalchemy.chemical_registration.merge_impact_reader``.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class MoleculeSummaryRow:
    """Raw molecule summary from the read model."""

    id: uuid.UUID
    registration_number: str
    name: str
    structure_status: str


@dataclass(frozen=True)
class MergeImpactCounts:
    """Raw impact counts from the read model."""

    batch_count: int
    readout_count: int
    curve_count: int
    collection_count: int
    flag_count: int
    active_sample_request_count: int
    terminal_sample_request_count: int
    synthesis_request_count: int
    active_synthesis_request_count: int
    route_count: int
    relationship_count: int


@runtime_checkable
class MergeImpactReader(Protocol):
    """Application-layer protocol for merge impact read-model queries."""

    async def get_molecule_summary(
        self, workspace_id: uuid.UUID, molecule_id: uuid.UUID
    ) -> MoleculeSummaryRow | None: ...

    async def get_impact_counts(
        self, workspace_id: uuid.UUID, source_molecule_id: uuid.UUID
    ) -> MergeImpactCounts: ...
