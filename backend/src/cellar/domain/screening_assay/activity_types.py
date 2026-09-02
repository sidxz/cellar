"""Read-model types for cross-context activity data queries.

These types bridge Chemical Registration and Screening & Assay contexts.
They are NOT aggregate roots — they are query result DTOs used by
MoleculeActivityService.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from cellar.domain.screening_assay.aggregation_types import AggregateStats


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
    # Fit-quality warning codes (e.g. "ec50_at_bound") so compact renderers
    # can flag extrapolated fits without re-querying the curve aggregate.
    fit_quality_warnings: list[str] | None = None


@dataclass(frozen=True)
class RunSummary:
    """One row in the cell tooltip's per-run table.

    Carries enough to render date / intercept value / qualifier / R² /
    curve class without a back-trip. ``intercept_values`` is the full
    per-curve list so the tooltip can show every intercept's per-run
    history, not just the column's primary one.
    """

    run_id: uuid.UUID
    run_date: date
    curve_id: uuid.UUID
    curve_class: str | None
    r_squared: float | None
    intercept_values: list[dict[str, Any]]


@dataclass(frozen=True)
class InterceptAggregate:
    """Per-intercept aggregation context. One per intercept the column shows.

    ``spec`` mirrors ``intercept_values[i].spec`` so cells can match by
    (kind, level). ``selected_value`` and ``selected_qualifier`` are the
    BE's already-applied truth — the FE renders them directly without
    re-deriving ND/GT from curve_class.
    """

    spec: dict[str, Any]
    selected_value: float | None
    selected_qualifier: str
    aggregate_stats: AggregateStats | None
    disagreement_flag: bool


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
    # Per-spec intercept values for dose_response sources. Same wire shape as
    # ``CurveDetail.intercept_values`` so the search grid can render one
    # column per protocol intercept (EC50, EC90, IC10, ...). Each entry is a
    # plain dict with keys ``spec`` (kind/level/basis/label), ``value``,
    # ``confidence_interval_low``, ``confidence_interval_high``, ``at_bound``.
    intercept_values: list[dict[str, Any]] | None = None
    # ---- NEW: multi-run aggregation context ----
    run_count: int = 1
    selection_rule: str | None = None
    runs: list[RunSummary] | None = None
    intercept_aggregates: list[InterceptAggregate] | None = None
    disagreement_flag: bool = False
    # ---- multi-run aggregate overlay (MEAN_ACROSS_RUNS / GEOMETRIC_MEAN) ----
    # When the cell aggregates multiple curves, the FE chart needs the OTHER
    # contributors so it can overlay them muted, plus an explicit marker for
    # the cell's aggregate value (the rep curve's per-intercept dashed line
    # points at the rep's intercept, not the aggregate). The representative
    # curve's own drawable shape is already on this object via ``raw_data`` /
    # ``curve_params`` / ``intercept_values`` — these two fields carry the
    # *extras* needed for an aggregate overlay. None on non-aggregate rules.
    additional_curves: list[dict[str, Any]] | None = None
    aggregate: dict[str, Any] | None = None


@dataclass(frozen=True)
class AnyProtocolEntry:
    """One protocol's measurement of a molecule, for the search grid's
    "Active in" column. Value is in the protocol's NATIVE unit; ``value_um``
    is the µM normalization used only for ordering."""

    protocol_id: uuid.UUID
    protocol_name: str
    protocol_type: str
    target_names: list[str]
    label: str  # "IC50", "EC90", "% Inhibition"
    source: str  # "dose_response" | "readout"
    readout_definition_id: uuid.UUID
    value: float | None
    qualifier: str | None
    unit: str | None
    value_um: float | None
    curve_class: str | None  # DR only
    run_count: int


@dataclass(frozen=True)
class AnyProtocolActivity:
    """Value of the ``any`` column: entries sorted best-first
    (``value_um`` asc, NULL last, then label)."""

    entries: list[AnyProtocolEntry]


@dataclass(frozen=True)
class ProtocolActivitySummary:
    """Activity summary for one protocol on one molecule."""

    protocol_id: uuid.UUID
    protocol_name: str
    protocol_type: str
    readouts: list[AggregatedReadout] = field(default_factory=list)
    best_curves: list[dict[str, Any]] = field(default_factory=list)
    # Protocol-declared intercept specs (EC50, EC90, IC10, ...). Drives the
    # per-Card dynamic column set on the molecule activity tab. Empty when
    # the protocol's DR readouts declare no explicit intercepts.
    intercepts: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True)
class ActivitySummary:
    """Full activity summary for a molecule across all protocols."""

    molecule_id: uuid.UUID
    protocols: list[ProtocolActivitySummary] = field(default_factory=list)
