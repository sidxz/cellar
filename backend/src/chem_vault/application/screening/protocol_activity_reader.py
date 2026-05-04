"""Read-model protocol for protocol activity queries.

The concrete implementation lives in
``infrastructure.persistence.sqlalchemy.screening_assay.protocol_activity_reader``.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Protocol, runtime_checkable


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
class NumericReadoutRow:
    """Aggregated numeric readout row from the read model."""

    molecule_id: uuid.UUID
    readout_name: str
    best: float | None
    mean: float | None
    n: int | None
    sd: float | None


@dataclass(frozen=True)
class DRAggRow:
    """Dose-response aggregation row from the read model."""

    molecule_id: uuid.UUID
    curve_type: str
    best: float | None
    geo_mean: float | None


@dataclass(frozen=True)
class BestParamsRow:
    """Best curve params row from the read model."""

    molecule_id: uuid.UUID
    curve_type: str
    curve_class: str | None
    hill_slope: float
    top: float
    bottom: float
    fitted_value: float
    r_squared: float
    raw_data: list[dict] | None
    batch_number: str | None


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
    ) -> ProtocolActivityData: ...
