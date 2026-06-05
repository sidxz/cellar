"""Cascade rules for chemical_registration tables.

Declares what happens to children of Molecule (and related aggregates) when
those parents are deleted via Tier-2 admin force-cascade.

Rules are derived from the actual ForeignKey declarations in:
  infrastructure/persistence/sqlalchemy/chemical_registration/models.py
  infrastructure/persistence/sqlalchemy/chemical_registration/disclosure_models.py
  infrastructure/persistence/sqlalchemy/chemical_registration/synthesis_route_models.py
  infrastructure/persistence/sqlalchemy/chemical_registration/bulk_registration_models.py

Schema notes / deviations from plan:
- molecule_relationships: actual FK columns are source_molecule_id / target_molecule_id,
  NOT from_molecule_id / to_molecule_id as in the original spec.
- synthesis_route_steps: actual table is reaction_steps with FK column route_id,
  NOT synthesis_route_steps.
- molecule_properties: table does not exist in the schema; rule removed.
- compound_flags.molecule_id: plain UUID, no FK constraint; rule removed.
- mixture_components: two FKs to molecules — mixture_molecule_id (CASCADE) and
  component_molecule_id (no ondelete); both added.
- merge_events: two FKs to molecules — source_molecule_id and target_molecule_id;
  rows are append-only audit records; SET_NULL is inappropriate so both CASCADE.
- disclosure_requests: also has resolved_to_molecule_id and matched_molecule_id FKs
  to molecules (nullable, no ondelete); SET_NULL on those references.
- bulk_registration_items.molecule_id: plain UUID, no FK constraint; rule removed.
"""

from cellar.domain.shared.cascade.actions import CascadeAction as A
from cellar.infrastructure.cascade.registry import register_rules
from cellar.infrastructure.cascade.rules import CascadeRule

register_rules(
    # -------------------------------------------------------------------------
    # Molecule identifiers (FK with ondelete=CASCADE)
    # -------------------------------------------------------------------------
    CascadeRule(
        child_table="molecule_identifiers",
        fk_column="molecule_id",
        parent_table="molecules",
        action=A.CASCADE,
        label_field="identifier",
        display_label="Identifiers",
    ),
    # -------------------------------------------------------------------------
    # Mixture components — two FKs to molecules
    # -------------------------------------------------------------------------
    # mixture_molecule_id → molecules.id (ondelete=CASCADE)
    CascadeRule(
        child_table="mixture_components",
        fk_column="mixture_molecule_id",
        parent_table="molecules",
        action=A.CASCADE,
        label_field=None,
        display_label="Mixture components (mixture side)",
    ),
    # component_molecule_id → molecules.id (no ondelete; informational reference)
    CascadeRule(
        child_table="mixture_components",
        fk_column="component_molecule_id",
        parent_table="molecules",
        action=A.CASCADE,
        label_field=None,
        display_label="Mixture components (component side)",
    ),
    # -------------------------------------------------------------------------
    # Molecule relationships — two FKs to molecules
    # -------------------------------------------------------------------------
    # source_molecule_id → molecules.id (no ondelete)
    CascadeRule(
        child_table="molecule_relationships",
        fk_column="source_molecule_id",
        parent_table="molecules",
        action=A.CASCADE,
        label_field=None,
        display_label="Outbound relationships",
    ),
    # target_molecule_id → molecules.id (no ondelete)
    CascadeRule(
        child_table="molecule_relationships",
        fk_column="target_molecule_id",
        parent_table="molecules",
        action=A.CASCADE,
        label_field=None,
        display_label="Inbound relationships",
    ),
    # -------------------------------------------------------------------------
    # Synthesis routes + reaction steps
    # -------------------------------------------------------------------------
    # SynthesisRouteModel.target_molecule_id → molecules.id (no ondelete)
    CascadeRule(
        child_table="synthesis_routes",
        fk_column="target_molecule_id",
        parent_table="molecules",
        action=A.CASCADE,
        label_field="name",
        display_label="Synthesis routes",
        recurse_into_entity="synthesis_route",
    ),
    # ReactionStepModel.route_id → synthesis_routes.id (ondelete=CASCADE)
    CascadeRule(
        child_table="reaction_steps",
        fk_column="route_id",
        parent_table="synthesis_routes",
        action=A.CASCADE,
        label_field=None,
        display_label="Reaction steps",
    ),
    # -------------------------------------------------------------------------
    # Disclosure requests — multiple FKs to molecules
    # -------------------------------------------------------------------------
    # DisclosureRequestModel.molecule_id → molecules.id (no ondelete)
    CascadeRule(
        child_table="disclosure_requests",
        fk_column="molecule_id",
        parent_table="molecules",
        action=A.CASCADE,
        label_field=None,
        display_label="Disclosure requests",
    ),
    # DisclosureRequestModel.resolved_to_molecule_id → molecules.id (nullable, no ondelete)
    CascadeRule(
        child_table="disclosure_requests",
        fk_column="resolved_to_molecule_id",
        parent_table="molecules",
        action=A.SET_NULL,
        label_field=None,
        display_label="Disclosure requests (resolved-to ref cleared)",
    ),
    # DisclosureRequestModel.matched_molecule_id → molecules.id (nullable, no ondelete)
    CascadeRule(
        child_table="disclosure_requests",
        fk_column="matched_molecule_id",
        parent_table="molecules",
        action=A.SET_NULL,
        label_field=None,
        display_label="Disclosure requests (matched ref cleared)",
    ),
    # DisclosureRequestModel.bulk_disclosure_id → bulk_disclosures.id (no ondelete)
    CascadeRule(
        child_table="disclosure_requests",
        fk_column="bulk_disclosure_id",
        parent_table="bulk_disclosures",
        action=A.CASCADE,
        label_field=None,
        display_label="Disclosure requests (bulk group)",
    ),
    # -------------------------------------------------------------------------
    # Merge events — append-only audit rows; both FKs cascade on molecule delete
    # -------------------------------------------------------------------------
    # MergeEventModel.source_molecule_id → molecules.id (no ondelete)
    CascadeRule(
        child_table="merge_events",
        fk_column="source_molecule_id",
        parent_table="molecules",
        action=A.CASCADE,
        label_field=None,
        display_label="Merge events (source ref)",
    ),
    # MergeEventModel.target_molecule_id → molecules.id (no ondelete)
    CascadeRule(
        child_table="merge_events",
        fk_column="target_molecule_id",
        parent_table="molecules",
        action=A.CASCADE,
        label_field=None,
        display_label="Merge events (target ref)",
    ),
)
