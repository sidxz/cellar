"""Read-model types for cross-context activity data queries.

These types bridge Chemical Registration and Screening & Assay contexts.
They are NOT aggregate roots — they are query result DTOs used by
MoleculeActivityService.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class AggregatedReadout:
    """Aggregated readout value for a molecule x readout definition."""

    readout_definition_id: uuid.UUID
    readout_name: str
    value: float | None
    qualifier: str | None
    unit: str | None
    aggregation: str  # mean, median, min, max, none
    data_point_count: int


@dataclass(frozen=True)
class CurveParams:
    """Curve fit parameters for dose-response display."""

    hill_slope: float
    top: float
    bottom: float
    num_points: int
    curve_class: str | None
    confidence_interval_low: float | None
    confidence_interval_high: float | None


@dataclass(frozen=True)
class ActivityValue:
    """Single activity value for display in search results or molecule detail."""

    value: float | None
    qualifier: str | None
    unit: str | None
    source: str  # "readout" or "dose_response"
    curve_type: str | None = None  # ic50, ec50 etc — only for dose_response
    r_squared: float | None = None  # only for dose_response
    data_point_count: int = 1
    raw_data: list[dict[str, float]] | None = None  # X/Y points for inline chart
    curve_params: CurveParams | None = None  # curve fit parameters


@dataclass(frozen=True)
class ProtocolActivitySummary:
    """Activity summary for one protocol on one molecule."""

    protocol_id: uuid.UUID
    protocol_name: str
    protocol_type: str
    readouts: list[AggregatedReadout] = field(default_factory=list)
    best_curves: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True)
class ActivitySummary:
    """Full activity summary for a molecule across all protocols."""

    molecule_id: uuid.UUID
    protocols: list[ProtocolActivitySummary] = field(default_factory=list)
