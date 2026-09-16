"""Cascade rules for screening_assay tables.

Declares what happens to children of Protocol, Run, Plate, etc., when those
parents are deleted via Tier-2 admin force-cascade.

Rules cover FK references (see
infrastructure/persistence/sqlalchemy/screening_assay/models.py) and id-only
references without an FK (compound flags, and measurements naming a molecule
or batch).
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import ColumnElement, Table, exists, or_

from cellar.domain.shared.cascade.actions import CascadeAction as A
from cellar.infrastructure.cascade.registry import register_rules
from cellar.infrastructure.cascade.rules import CascadeRule, any_id
from cellar.infrastructure.persistence.sqlalchemy.screening_assay.models import (
    DoseResponseCurveModel,
    PlateModel,
    ReadoutDataModel,
    WellModel,
)


def _runs_with_data_for_molecules(
    runs: Table, molecule_ids: Sequence[uuid.UUID]
) -> ColumnElement[bool]:
    readouts = ReadoutDataModel.__table__
    curves = DoseResponseCurveModel.__table__
    return or_(
        exists().where(
            readouts.c.run_id == runs.c.id, any_id(readouts.c.molecule_id, molecule_ids)
        ),
        exists().where(curves.c.run_id == runs.c.id, any_id(curves.c.molecule_id, molecule_ids)),
    )


def _runs_with_data_for_batches(
    runs: Table, batch_ids: Sequence[uuid.UUID]
) -> ColumnElement[bool]:
    readouts = ReadoutDataModel.__table__
    curves = DoseResponseCurveModel.__table__
    plates = PlateModel.__table__
    wells = WellModel.__table__
    return or_(
        exists().where(readouts.c.run_id == runs.c.id, any_id(readouts.c.batch_id, batch_ids)),
        exists().where(curves.c.run_id == runs.c.id, any_id(curves.c.batch_id, batch_ids)),
        exists().where(
            plates.c.run_id == runs.c.id,
            wells.c.plate_id == plates.c.id,
            any_id(wells.c.batch_id, batch_ids),
        ),
    )


register_rules(
    # -------------------------------------------------------------------------
    # Protocol children
    # -------------------------------------------------------------------------
    # ReadoutDefinitionModel.protocol_id → protocols (ondelete=CASCADE)
    # Owned entity; also parent of readout_data rows via readout_definition_id.
    CascadeRule(
        child_table="readout_definitions",
        fk_column="protocol_id",
        parent_table="protocols",
        action=A.CASCADE,
        label_field="name",
        display_label="Readout definitions",
        recurse_into_entity="readout_definition",
    ),
    # ConditionDefinitionModel.protocol_id → protocols (ondelete=CASCADE)
    # Owned entity; no further children.
    CascadeRule(
        child_table="condition_definitions",
        fk_column="protocol_id",
        parent_table="protocols",
        action=A.CASCADE,
        label_field="name",
        display_label="Condition definitions",
    ),
    # protocol_projects association table → protocols (ondelete=CASCADE)
    # Pure join table; no label column.
    CascadeRule(
        child_table="protocol_projects",
        fk_column="protocol_id",
        parent_table="protocols",
        action=A.CASCADE,
        label_field=None,
        display_label="Protocol-project links",
    ),
    # RunModel.protocol_id → protocols (no ondelete clause — application-level)
    # Run is its own aggregate root; protocol deletion must cascade through runs
    # and then through each run's plates, wells, readout_data, and curves.
    # label_field="notes" — runs have no `name` column.
    CascadeRule(
        child_table="runs",
        fk_column="protocol_id",
        parent_table="protocols",
        action=A.CASCADE,
        label_field="notes",
        display_label="Runs",
        recurse_into_entity="run",
    ),
    # DoseResponseCurveModel.protocol_id → protocols (no ondelete clause)
    # Curves reference both protocol and run; delete when protocol is deleted.
    CascadeRule(
        child_table="dose_response_curves",
        fk_column="protocol_id",
        parent_table="protocols",
        action=A.CASCADE,
        label_field=None,
        display_label="Dose-response curves (protocol ref)",
    ),
    # -------------------------------------------------------------------------
    # Run children
    # -------------------------------------------------------------------------
    # PlateModel.run_id → runs (ondelete=CASCADE)
    # Owned entity; parent of wells.
    CascadeRule(
        child_table="plates",
        fk_column="run_id",
        parent_table="runs",
        action=A.CASCADE,
        label_field="barcode",
        display_label="Plates",
        recurse_into_entity="plate",
    ),
    # PlateModel.registered_plate_id → registered_plates (ondelete=SET NULL, S15)
    # Optional link to the physical inventory plate. Deleting the inventory
    # plate must never delete a run's plate — the run keeps its data and only
    # loses the link.
    CascadeRule(
        child_table="plates",
        fk_column="registered_plate_id",
        parent_table="registered_plates",
        action=A.SET_NULL,
        label_field="barcode",
        display_label="Run plates (inventory link cleared)",
    ),
    # ReadoutDataModel.run_id → runs (no ondelete clause — application-level)
    # Bulk measurement rows owned by the run.
    CascadeRule(
        child_table="readout_data",
        fk_column="run_id",
        parent_table="runs",
        action=A.CASCADE,
        label_field=None,
        display_label="Readout data",
    ),
    # DoseResponseCurveModel.run_id → runs (no ondelete clause — application-level)
    CascadeRule(
        child_table="dose_response_curves",
        fk_column="run_id",
        parent_table="runs",
        action=A.CASCADE,
        label_field=None,
        display_label="Dose-response curves",
    ),
    # -------------------------------------------------------------------------
    # Plate children
    # -------------------------------------------------------------------------
    # WellModel.plate_id → plates (ondelete=CASCADE)
    # Wells have no FK-declared children (readout_data.well_id carries no FK).
    CascadeRule(
        child_table="wells",
        fk_column="plate_id",
        parent_table="plates",
        action=A.CASCADE,
        label_field=None,
        display_label="Wells",
    ),
    # -------------------------------------------------------------------------
    # Readout definition children
    # -------------------------------------------------------------------------
    # ReadoutDataModel.readout_definition_id → readout_definitions (no ondelete)
    # Measurement rows keyed to a specific readout column definition.
    CascadeRule(
        child_table="readout_data",
        fk_column="readout_definition_id",
        parent_table="readout_definitions",
        action=A.CASCADE,
        label_field=None,
        display_label="Readout data (definition ref)",
    ),
    # -------------------------------------------------------------------------
    # Plate template loose reference (SET NULL)
    # -------------------------------------------------------------------------
    # RunModel.plate_template_id → plate_templates (ondelete=SET NULL)
    # Template is a shared reference, not an owned child.
    CascadeRule(
        child_table="runs",
        fk_column="plate_template_id",
        parent_table="plate_templates",
        action=A.SET_NULL,
        label_field="notes",
        display_label="Runs (template link cleared)",
    ),
    # -------------------------------------------------------------------------
    # Self-referential lineage links (SET NULL)
    # -------------------------------------------------------------------------
    # Versioned successors point back at their predecessor via parent_*_id.
    # When the predecessor is admin-deleted, the successor must survive — it
    # owns its own runs/data and is not a child in the ownership sense.
    # SET NULL clears the lineage link so the FK no longer blocks deletion.
    # The null_ops phase runs before deletes, so this also handles the case
    # where a whole versioning chain is collected for deletion at once.
    # ProtocolModel.parent_protocol_id → protocols (no ondelete clause)
    CascadeRule(
        child_table="protocols",
        fk_column="parent_protocol_id",
        parent_table="protocols",
        action=A.SET_NULL,
        label_field="name",
        display_label="Successor protocols (lineage link cleared)",
    ),
    # RunModel.parent_run_id → runs (no ondelete clause)
    CascadeRule(
        child_table="runs",
        fk_column="parent_run_id",
        parent_table="runs",
        action=A.SET_NULL,
        label_field="notes",
        display_label="Successor runs (lineage link cleared)",
    ),
    # -------------------------------------------------------------------------
    # Compound flags (no FK)
    # -------------------------------------------------------------------------
    # CompoundFlagModel.protocol_id: a user's flag on a compound in a protocol,
    # meaningless once the protocol is gone.
    CascadeRule(
        child_table="compound_flags",
        parent_table="protocols",
        action=A.CASCADE,
        fk_column="protocol_id",
        display_label="Compound flags",
    ),
    # CompoundFlagModel.molecule_id (no FK): the flag means nothing without its compound.
    CascadeRule(
        child_table="compound_flags",
        parent_table="molecules",
        action=A.CASCADE,
        fk_column="molecule_id",
        display_label="Compound flags",
    ),
    # -------------------------------------------------------------------------
    # Runs holding measurements for a force-deleted molecule or batch (no FK)
    # -------------------------------------------------------------------------
    # readout_data.molecule_id and dose_response_curves.molecule_id. Deleting a
    # compound must not pull data out of runs, and a refit would re-create its
    # curves anyway. Merge the molecule, or force-delete the runs first.
    CascadeRule(
        child_table="runs",
        parent_table="molecules",
        action=A.BLOCK,
        match=_runs_with_data_for_molecules,
        covers=("readout_data.molecule_id", "dose_response_curves.molecule_id"),
        label_field="run_date",
        display_label="Runs with data for this molecule",
    ),
    # Wells store only the batch, so a deleted batch leaves a plate map with no
    # compound identity at all.
    CascadeRule(
        child_table="runs",
        parent_table="batches",
        action=A.BLOCK,
        match=_runs_with_data_for_batches,
        covers=("wells.batch_id", "readout_data.batch_id", "dose_response_curves.batch_id"),
        label_field="run_date",
        display_label="Runs with data for this molecule's batches",
    ),
)
