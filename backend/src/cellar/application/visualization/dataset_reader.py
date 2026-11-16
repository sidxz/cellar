"""Read-model port for the visualization workbench's datasets.

The concrete implementation lives in
``infrastructure.persistence.sqlalchemy.visualization.dataset_reader``.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Protocol, runtime_checkable

from cellar.application.screening.compound_curves_reader import CurveRow


@dataclass(frozen=True)
class RunInfo:
    id: uuid.UUID
    protocol_id: uuid.UUID
    run_date: date
    operator_id: uuid.UUID
    status: str
    conditions: dict[str, Any] | None
    created_at: datetime


@dataclass(frozen=True)
class ReadoutDefInfo:
    id: uuid.UUID
    protocol_id: uuid.UUID
    name: str
    data_type: str
    unit: str | None
    display_order: int
    dose_unit: str | None = None  # the owning protocol's
    curve_type: str | None = None  # dose_response_config.curve_type
    melt_measure: str | None = None  # melt_config.measure


@dataclass(frozen=True)
class CompoundInfo:
    registration_number: str
    smiles: str | None
    molecular_weight: float | None
    logp: float | None
    tpsa: float | None
    hbd: int | None
    hba: int | None
    rotatable_bonds: int | None
    aromatic_rings: int | None


@dataclass(frozen=True)
class WellValueRow:
    """One ``readout_data`` row with its well, plate, compound and batch context."""

    run_id: uuid.UUID
    well_id: uuid.UUID | None
    plate_id: uuid.UUID | None
    plate_number: int | None
    plate_barcode: str | None
    plate_format: str | None
    holder_rows: int | None
    holder_columns: int | None
    well_row: str | None
    well_column: int | None
    well_type: str | None
    dose: float | None
    well_label: str | None
    molecule_id: uuid.UUID | None
    registration_number: str | None
    smiles: str | None
    batch_id: uuid.UUID | None
    batch_number: str | None
    readout_definition_id: uuid.UUID
    normalization_applied: str | None
    value_numeric: float | None
    value_qualifier: str | None
    value_text: str | None
    is_outlier: bool
    created_at: datetime


@runtime_checkable
class VisualizationDatasetReader(Protocol):
    async def runs_for_protocol(
        self, workspace_id: uuid.UUID, protocol_id: uuid.UUID
    ) -> list[RunInfo] | None:
        """All runs of the protocol; ``None`` when the protocol is not in the workspace."""
        ...

    async def runs_by_ids(
        self, workspace_id: uuid.UUID, run_ids: list[uuid.UUID]
    ) -> list[RunInfo]:
        """Runs of the workspace among ``run_ids`` (foreign ids are simply absent)."""
        ...

    async def readout_definitions(
        self, workspace_id: uuid.UUID, protocol_ids: list[uuid.UUID]
    ) -> list[ReadoutDefInfo]: ...

    async def count_wells_rows(
        self, workspace_id: uuid.UUID, run_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, int]:
        """Rows each run contributes at Wells level: distinct wells plus distinct
        well-less (molecule, batch) keys."""
        ...

    async def fetch_well_values(
        self, workspace_id: uuid.UUID, run_ids: list[uuid.UUID]
    ) -> list[WellValueRow]:
        """Every readout value of the runs, ordered by run, plate, row, column, created_at."""
        ...

    async def fetch_curves(
        self, workspace_id: uuid.UUID, run_ids: list[uuid.UUID]
    ) -> list[CurveRow]:
        """Every fitted curve of the runs: one per (run, molecule, batch, readout)."""
        ...

    async def compound_info(
        self, workspace_id: uuid.UUID, molecule_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, CompoundInfo]:
        """Registration number, structure and descriptors of the workspace's molecules."""
        ...

    async def batch_numbers(
        self, workspace_id: uuid.UUID, batch_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, str]: ...
