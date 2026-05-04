"""Read-model protocol for compound curves queries.

The concrete implementation lives in
``infrastructure.persistence.sqlalchemy.screening_assay.compound_curves_reader``.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable


@dataclass(frozen=True)
class CurveRow:
    """Raw dose-response curve row from the read model."""

    id: uuid.UUID
    workspace_id: uuid.UUID
    molecule_id: uuid.UUID
    batch_id: uuid.UUID
    protocol_id: uuid.UUID
    run_id: uuid.UUID
    curve_type: str | None
    fitted_value: float | None
    fitted_unit: str | None
    hill_slope: float | None
    top: float | None
    bottom: float | None
    r_squared: float | None
    confidence_interval_low: float | None
    confidence_interval_high: float | None
    num_points: int | None
    curve_class: str | None
    raw_data: Any | None
    excluded_points: Any | None


@runtime_checkable
class CompoundCurvesReader(Protocol):
    """Application-layer protocol for compound curves read-model queries."""

    async def get_curves(
        self,
        workspace_id: uuid.UUID,
        protocol_id: uuid.UUID,
        molecule_id: uuid.UUID,
    ) -> list[CurveRow]: ...
