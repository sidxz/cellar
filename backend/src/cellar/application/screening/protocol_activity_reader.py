"""Read-model protocol for protocol activity queries.

The concrete implementation lives in
``infrastructure.persistence.sqlalchemy.screening_assay.protocol_activity_reader``.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Literal, Protocol, runtime_checkable

from cellar.domain.screening_assay.activity_types import ReplicateStats


@dataclass(frozen=True)
class ProtocolRow:
    """Minimal protocol info from the read model."""

    id: uuid.UUID
    readout_definitions: list[Any]


@dataclass(frozen=True)
class MoleculeBaseRow:
    """Per-molecule base data from the read model."""

    molecule_id: uuid.UUID
    molecule_name: str | None
    registration_number: str | None
    smiles: str | None
    run_count: int
    last_tested: date | None


@dataclass(frozen=True)
class AggregateScope:
    """Which runs one aggregation reads and what it groups by.

    Every group is one (molecule, readout, layer) — layers and condition sets
    are never pooled. ``statuses=None`` reads every run status; ``run_ids``
    narrows to those runs. ``grain`` adds the batch (``"batch"``) or batch and
    run (``"run"``) to the group; ``by_conditions`` adds the run's condition set.
    ``exclude_censored`` keeps ``>``/``<`` values out of best/low/mean/n/sd (they
    are only counted) and adds the median and geomean of the unqualified values;
    the Activity summary turns it off to keep averaging them.
    """

    statuses: tuple[str, ...] | None
    run_ids: tuple[uuid.UUID, ...] | None = None
    grain: Literal["compound", "batch", "run"] = "compound"
    by_conditions: bool = False
    exclude_censored: bool = True


@dataclass(frozen=True)
class NumericReadoutRow:
    """Aggregated numeric readout row from the read model.

    ``best``/``low``/``mean``/``n``/``sd`` cover the unqualified values (every
    value when the scope keeps censored ones); ``gt_*``/``lt_*`` count the
    ``>``/``>=`` and ``<``/``<=`` values and keep their tightest-true bounds.
    ``batch_id``/``run_id``/``conditions`` are set only when the scope groups by them.
    """

    molecule_id: uuid.UUID
    readout_name: str
    best: float | None  # the group's maximum
    mean: float | None
    n: int | None
    sd: float | None
    low: float | None = None  # the group's minimum
    layer: str | None = None  # normalization_applied; None = the raw layer
    readout_definition_id: uuid.UUID | None = None
    batch_id: uuid.UUID | None = None
    run_id: uuid.UUID | None = None
    conditions: dict[str, Any] | None = None  # the condition set; {} = none
    gt_count: int = 0
    gt_bound: float | None = None  # the largest ">" value
    lt_count: int = 0
    lt_bound: float | None = None  # the smallest "<" value
    # Only when the scope excludes censored values (the workbench path):
    median: float | None = None
    geomean: float | None = None  # over the unqualified values > 0
    nonpositive_count: int = 0  # unqualified values <= 0, left out of the geomean

    def stats(self) -> ReplicateStats:
        """The group as replicate stats for ``combine_replicates``."""
        return ReplicateStats(
            eq_count=self.n or 0,
            eq_mean=self.mean,
            eq_median=self.median,
            eq_min=self.low,
            eq_max=self.best,
            eq_geomean=self.geomean,
            gt_count=self.gt_count,
            gt_max_bound=self.gt_bound,
            lt_count=self.lt_count,
            lt_min_bound=self.lt_bound,
        )


@dataclass(frozen=True)
class DRAggRow:
    """Dose-response aggregation row from the read model.

    Grouped by readout-def, not curve_type — a protocol can have N DR
    readouts sharing one curve_type (target IC50 + counter-screen IC50)
    and grouping by curve_type would collapse them into one row.
    """

    molecule_id: uuid.UUID
    readout_definition_id: uuid.UUID
    best: float | None  # over active curves (not inactive, fitted value > 0)
    geo_mean: float | None  # None when no curve is active
    batch_id: uuid.UUID | None = None
    run_id: uuid.UUID | None = None
    conditions: dict[str, Any] | None = None
    n_tested: int = 0  # every curve
    n_inactive: int = 0  # curve_class "inactive"
    n_used: int = 0  # active curves, the ones best/geo_mean read


@dataclass(frozen=True)
class ActivityAggregates:
    """One ``AggregateScope``'s numeric and dose-response groups."""

    numeric_rows: list[NumericReadoutRow]
    dr_agg_rows: list[DRAggRow]


@dataclass(frozen=True)
class BestParamsRow:
    """Best curve params row from the read model."""

    molecule_id: uuid.UUID
    readout_definition_id: uuid.UUID
    curve_class: str | None
    hill_slope: float
    top: float
    bottom: float
    fitted_value: float
    r_squared: float
    raw_data: list[dict] | None
    batch_number: str | None
    # Per-spec intercepts (IC50/IC90/EC50/EC90/...) from the same Hill fit.
    # None on legacy curves fit before multi-intercept support. The
    # use-case layer flattens these into ``CurveParams.intercept_values``
    # so each row of the activity grid can read EC90 alongside EC50.
    intercept_values: list[dict] | None


@dataclass(frozen=True)
class ProtocolActivityData:
    """All raw data needed to build the activity summary."""

    protocol: ProtocolRow | None
    molecule_rows: list[MoleculeBaseRow] = field(default_factory=list)
    synonym_map: dict[uuid.UUID, list[str]] = field(default_factory=dict)
    numeric_rows: list[NumericReadoutRow] = field(default_factory=list)
    dr_agg_rows: list[DRAggRow] = field(default_factory=list)
    best_params_rows: list[BestParamsRow] = field(default_factory=list)


@runtime_checkable
class ProtocolActivityReader(Protocol):
    """Application-layer protocol for protocol activity read-model queries."""

    async def get_activity_data(
        self,
        workspace_id: uuid.UUID,
        protocol_id: uuid.UUID,
        valid_statuses: tuple[str, ...],
    ) -> ProtocolActivityData:
        """The Activity summary's data. Its numeric rows average every value,
        censored ones included (``exclude_censored=False``)."""
        ...

    async def get_aggregates(
        self,
        workspace_id: uuid.UUID,
        protocol_id: uuid.UUID,
        scope: AggregateScope,
    ) -> ActivityAggregates: ...
