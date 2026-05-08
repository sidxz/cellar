"""Cascade rules for inventory context tables.

Declares what happens to children of Batch, Sample, etc., when those parents
are deleted via Tier-2 admin force-cascade.

Rules are derived from the actual ForeignKey declarations in:
  infrastructure/persistence/sqlalchemy/inventory/models.py
  infrastructure/persistence/sqlalchemy/inventory/shipment_models.py
  infrastructure/persistence/sqlalchemy/inventory/sample_request_models.py

Schema notes / deviations from plan:
- shipment_items.sample_id: plain UUID, no FK constraint declared; rule removed.
- sample_requests: no sample_id FK column at all (fulfilled_sample_id is plain UUID);
  rule for SET_NULL on sample_id removed.
- sample_requests.molecule_id: plain UUID, no FK constraint; no cascade rule.
- batches.molecule_id: no ondelete clause but is a FK — CASCADE rule added.
"""
from chem_vault.domain.shared.cascade.actions import CascadeAction as A
from chem_vault.infrastructure.cascade.rules import CascadeRule
from chem_vault.infrastructure.cascade.registry import register_rules


register_rules(
    # -------------------------------------------------------------------------
    # Batch children — Batch is child of Molecule
    # -------------------------------------------------------------------------
    # BatchModel.molecule_id → molecules.id (no ondelete clause)
    CascadeRule(
        child_table="batches",
        fk_column="molecule_id",
        parent_table="molecules",
        action=A.CASCADE,
        label_field="batch_number",
        display_label="Batches",
        recurse_into_entity="batch",
    ),

    # -------------------------------------------------------------------------
    # Sample children — Sample is child of Batch
    # -------------------------------------------------------------------------
    # SampleModel.batch_id → batches.id (no ondelete clause)
    CascadeRule(
        child_table="samples",
        fk_column="batch_id",
        parent_table="batches",
        action=A.CASCADE,
        label_field="barcode",
        display_label="Samples",
        recurse_into_entity="sample",
    ),
)
