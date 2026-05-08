"""Cascade rules for research_organization context tables.

Declares what happens to children of Project, Molecule (cross-context), etc.,
when those parents are deleted via Tier-2 admin force-cascade.

Rules are derived from the actual ForeignKey declarations in:
  infrastructure/persistence/sqlalchemy/research_organization/models.py

Schema notes / deviations from plan:
- Association table is molecule_projects (not project_molecules) — corrected.
- saved_searches has project_id FK to projects (ondelete=SET NULL), not a
  protocol_id FK to protocols as stated in the spec; rule corrected accordingly.
- CollectionMoleculeModel.molecule_id → molecules.id (ondelete=CASCADE) — added.
- CollectionModel.project_id → projects.id (ondelete=SET NULL) — added.
- ProjectMemberModel.project_id → projects.id (ondelete=CASCADE) — added.
"""
from chem_vault.domain.shared.cascade.actions import CascadeAction as A
from chem_vault.infrastructure.cascade.rules import CascadeRule
from chem_vault.infrastructure.cascade.registry import register_rules


register_rules(
    # -------------------------------------------------------------------------
    # molecule_projects association table (FK on both sides with ondelete=CASCADE)
    # -------------------------------------------------------------------------
    CascadeRule(
        child_table="molecule_projects",
        fk_column="molecule_id",
        parent_table="molecules",
        action=A.CASCADE,
        label_field=None,
        display_label="Project memberships",
    ),
    CascadeRule(
        child_table="molecule_projects",
        fk_column="project_id",
        parent_table="projects",
        action=A.CASCADE,
        label_field=None,
        display_label="Project–molecule links",
    ),

    # -------------------------------------------------------------------------
    # collection_molecules join table
    # -------------------------------------------------------------------------
    # CollectionMoleculeModel.molecule_id → molecules.id (ondelete=CASCADE)
    CascadeRule(
        child_table="collection_molecules",
        fk_column="molecule_id",
        parent_table="molecules",
        action=A.CASCADE,
        label_field=None,
        display_label="Collection memberships",
    ),
    # CollectionMoleculeModel.collection_id → collections.id (ondelete=CASCADE)
    CascadeRule(
        child_table="collection_molecules",
        fk_column="collection_id",
        parent_table="collections",
        action=A.CASCADE,
        label_field=None,
        display_label="Collection–molecule links",
    ),

    # -------------------------------------------------------------------------
    # Collection parent references
    # -------------------------------------------------------------------------
    # CollectionModel.project_id → projects.id (ondelete=SET NULL)
    CascadeRule(
        child_table="collections",
        fk_column="project_id",
        parent_table="projects",
        action=A.SET_NULL,
        label_field="name",
        display_label="Collections (project scope cleared)",
    ),

    # -------------------------------------------------------------------------
    # Project members
    # -------------------------------------------------------------------------
    # ProjectMemberModel.project_id → projects.id (ondelete=CASCADE)
    CascadeRule(
        child_table="project_members",
        fk_column="project_id",
        parent_table="projects",
        action=A.CASCADE,
        label_field=None,
        display_label="Project members",
    ),

    # -------------------------------------------------------------------------
    # Saved searches — scoped to a project (SET NULL on project delete)
    # -------------------------------------------------------------------------
    # SavedSearchModel.project_id → projects.id (ondelete=SET NULL)
    # Note: spec listed protocol_id FK which does not exist; actual FK is project_id.
    CascadeRule(
        child_table="saved_searches",
        fk_column="project_id",
        parent_table="projects",
        action=A.SET_NULL,
        label_field="name",
        display_label="Saved searches (project scope cleared)",
    ),
)
