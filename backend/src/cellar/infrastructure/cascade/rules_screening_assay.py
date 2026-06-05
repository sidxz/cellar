"""Cascade rules for screening_assay tables.

Declares what happens to children of Protocol, Run, Plate, etc., when those
parents are deleted via Tier-2 admin force-cascade.

Rules are derived from the actual ForeignKey declarations in
infrastructure/persistence/sqlalchemy/screening_assay/models.py.
"""

from cellar.domain.shared.cascade.actions import CascadeAction as A
from cellar.infrastructure.cascade.registry import register_rules
from cellar.infrastructure.cascade.rules import CascadeRule

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
)
