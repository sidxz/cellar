"""ReadoutData entity — individual measurement point from a run."""

from __future__ import annotations

import uuid
from datetime import datetime

from cellar.domain.screening_assay.enums import ReadoutNormalization
from cellar.domain.shared.entity import Entity
from cellar.domain.shared.value_objects import QualifiedValue


class ReadoutData(Entity):
    """A single readout measurement recorded against a well/molecule/batch.

    NOT an AggregateRoot — lives outside the Run aggregate boundary.
    Data lock enforcement is external via DataLockGuard.

    No domain events or state machine — this is a simple data entity
    that stores raw/processed assay measurements.
    """

    def __init__(
        self,
        *,
        id: uuid.UUID | None = None,
        workspace_id: uuid.UUID,
        run_id: uuid.UUID,
        well_id: uuid.UUID | None = None,
        molecule_id: uuid.UUID | None = None,
        batch_id: uuid.UUID | None = None,
        readout_definition_id: uuid.UUID,
        value: QualifiedValue | None = None,
        value_text: str | None = None,
        is_outlier: bool = False,
        is_computed: bool = False,
        normalization_applied: ReadoutNormalization | None = None,
        created_at: datetime | None = None,
        updated_at: datetime | None = None,
    ) -> None:
        super().__init__(id=id, created_at=created_at, updated_at=updated_at)

        self.workspace_id = workspace_id
        self.run_id = run_id
        self.well_id = well_id
        self.molecule_id = molecule_id
        self.batch_id = batch_id
        self.readout_definition_id = readout_definition_id
        self.value = value
        self.value_text = value_text
        self.is_outlier = is_outlier
        self.is_computed = is_computed
        # Identifies which normalization formula produced this row.
        # None for raw rows (is_computed=False); the formula for computed rows.
        self.normalization_applied = normalization_applied
