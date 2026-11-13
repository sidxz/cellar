"""Read-model protocol for the positions of a protocol that have measured curves.

The concrete implementation lives in
``infrastructure.persistence.sqlalchemy.screening_assay.curve_position_reader``.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from typing import Protocol, runtime_checkable

from cellar.application.screening.plate_map_reader import WellMapEntry
from cellar.domain.screening_assay.measured_curve import CurveChannel


@dataclass(frozen=True)
class CurveRun:
    """A run of the protocol that has curves. A run has no name; it is told apart
    by its date, operator, status and notes."""

    run_id: uuid.UUID
    run_date: date
    operator: uuid.UUID
    status: str
    notes: str | None
    holder_kind: str
    holder_rows: int | None
    holder_columns: int | None
    holder_label: str
    channels: tuple[CurveChannel, ...]  # ordered by channel order
    position_count: int  # positions with at least one curve


@dataclass(frozen=True)
class CurvePosition:
    run_id: uuid.UUID
    well: WellMapEntry


@dataclass(frozen=True)
class CurvePositions:
    protocol_id: uuid.UUID
    dose_unit: str
    # Every run of the protocol that has curves: run_date descending, then created_at descending.
    runs: tuple[CurveRun, ...]
    # In the order of runs, then row (A before B before AA), then column.
    positions: tuple[CurvePosition, ...]


@runtime_checkable
class CurvePositionReader(Protocol):
    """Finds positions with curves without loading the curves themselves."""

    async def find(
        self,
        workspace_id: uuid.UUID,
        protocol_id: uuid.UUID,
        *,
        run_ids: Sequence[uuid.UUID] = (),
        molecule_ids: Sequence[uuid.UUID] = (),
    ) -> CurvePositions | None:
        """None when the protocol is not in the workspace. ``runs`` ignores the filters.
        ``positions`` is empty without a filter; with ``run_ids`` it holds those runs'
        positions, with ``molecule_ids`` those whose batch belongs to one of the compounds,
        with both those satisfying both; then each contributing run's reference positions
        are added. Only positions with at least one curve are returned."""
        ...
