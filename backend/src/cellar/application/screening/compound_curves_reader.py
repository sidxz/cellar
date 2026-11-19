"""Read-model protocol for compound curves queries.

The concrete implementation lives in
``infrastructure.persistence.sqlalchemy.screening_assay.compound_curves_reader``.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from cellar.domain.screening_assay.curve_fitting import InterceptValue


@dataclass(frozen=True)
class CurveRow:
    """Raw dose-response curve row from the read model."""

    id: uuid.UUID
    workspace_id: uuid.UUID
    molecule_id: uuid.UUID
    batch_id: uuid.UUID
    protocol_id: uuid.UUID
    run_id: uuid.UUID
    readout_definition_id: uuid.UUID
    curve_type: str | None
    fitted_value: float | None
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
    intercept_values: Any | None = None  # [{spec, value, at_bound, …}]; the first is primary


@dataclass(frozen=True)
class CompoundCurveRow(CurveRow):
    """A curve with its batch's number (``None`` when the batch is not the workspace's)
    and its intercepts read as the curve repository reads them (one stored before
    intercepts were stored reads its fitted value as its one)."""

    batch_number: str | None = None
    intercepts: tuple[InterceptValue, ...] = ()


@runtime_checkable
class CompoundCurvesReader(Protocol):
    """Application-layer protocol for compound curves read-model queries."""

    async def get_curves(
        self,
        workspace_id: uuid.UUID,
        protocol_id: uuid.UUID,
        molecule_id: uuid.UUID,
    ) -> list[CompoundCurveRow]: ...
