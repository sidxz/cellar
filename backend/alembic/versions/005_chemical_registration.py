"""Chemical registration tables — molecules, identifiers, mixture components, relationships.

Revision ID: 005
Revises: 004
Create Date: 2026-04-04
"""

import sqlalchemy as sa
from alembic import op

revision: str = "005"
down_revision: str = "004"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "molecules",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("workspace_id", sa.Uuid(), nullable=False, index=True),
        sa.Column("registration_number", sa.String(50), nullable=False),
        sa.Column("name", sa.String(500), nullable=False),
        sa.Column("molecule_type", sa.String(50), nullable=False),
        # Structure
        sa.Column("smiles", sa.Text(), nullable=True),
        sa.Column("cxsmiles", sa.Text(), nullable=True),
        sa.Column("inchi", sa.Text(), nullable=True),
        sa.Column("inchi_key", sa.String(27), nullable=True),
        sa.Column("molfile", sa.Text(), nullable=True),
        # Descriptors
        sa.Column("molecular_formula", sa.String(100), nullable=True),
        sa.Column("molecular_weight", sa.Float(), nullable=True),
        sa.Column("exact_mass", sa.Float(), nullable=True),
        sa.Column("logp", sa.Float(), nullable=True),
        sa.Column("tpsa", sa.Float(), nullable=True),
        sa.Column("hbd", sa.Integer(), nullable=True),
        sa.Column("hba", sa.Integer(), nullable=True),
        sa.Column("rotatable_bonds", sa.Integer(), nullable=True),
        sa.Column("aromatic_rings", sa.Integer(), nullable=True),
        sa.Column("ring_count", sa.Integer(), nullable=True),
        sa.Column("heavy_atom_count", sa.Integer(), nullable=True),
        sa.Column("ro5_violations", sa.Integer(), nullable=True),
        # Predicted properties
        sa.Column("logd", sa.Float(), nullable=True),
        sa.Column("pka", sa.Float(), nullable=True),
        sa.Column("logs", sa.Float(), nullable=True),
        sa.Column("prediction_source", sa.String(100), nullable=True),
        sa.Column("predicted_at", sa.DateTime(timezone=True), nullable=True),
        # Fingerprints (binary)
        sa.Column("fp_morgan", sa.LargeBinary(), nullable=True),
        sa.Column("fp_rdkit", sa.LargeBinary(), nullable=True),
        sa.Column("fp_maccs", sa.LargeBinary(), nullable=True),
        sa.Column("fp_topological_torsion", sa.LargeBinary(), nullable=True),
        sa.Column("fp_atom_pair", sa.LargeBinary(), nullable=True),
        # State machines
        sa.Column("structure_status", sa.String(20), nullable=False, server_default="disclosed"),
        sa.Column("registration_status", sa.String(20), nullable=False, server_default="approved"),
        sa.Column("synthesis_status", sa.String(20), nullable=False, server_default="synthesized"),
        sa.Column("lifecycle_stage", sa.String(30), nullable=False, server_default="registered"),
        # Other fields
        sa.Column("stereochemistry", sa.String(20), nullable=True),
        sa.Column("sequence", sa.Text(), nullable=True),
        sa.Column("structure_image_key", sa.String(500), nullable=True),
        sa.Column("tags", sa.JSON(), nullable=True),
        sa.Column("custom_fields", sa.JSON(), nullable=True),
        sa.Column("invention_date", sa.Date(), nullable=True),
        sa.Column("disclosed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("disclosed_by", sa.Uuid(), nullable=True),
        sa.Column("merged_into_id", sa.Uuid(), nullable=True),
        sa.Column(
            "originating_org_id",
            sa.Uuid(),
            sa.ForeignKey("organizations.id"),
            nullable=False,
        ),
        # Standard columns
        sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        # Constraints
        sa.UniqueConstraint("workspace_id", "registration_number", name="uq_mol_ws_regnum"),
    )

    # Indexes
    op.create_index("ix_molecules_inchi_key", "molecules", ["workspace_id", "inchi_key"])
    op.create_index("ix_molecules_merged_into_id", "molecules", ["merged_into_id"])

    # Molecule identifiers
    op.create_table(
        "molecule_identifiers",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "molecule_id",
            sa.Uuid(),
            sa.ForeignKey("molecules.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("identifier", sa.String(255), nullable=False),
        sa.Column("identifier_type", sa.String(50), nullable=False),
        sa.Column("source", sa.String(255), nullable=False),
        sa.Column("registered_by", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("molecule_id", "identifier", name="uq_mol_ident"),
    )

    # Mixture components
    op.create_table(
        "mixture_components",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "mixture_molecule_id",
            sa.Uuid(),
            sa.ForeignKey("molecules.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "component_molecule_id",
            sa.Uuid(),
            sa.ForeignKey("molecules.id"),
            nullable=False,
        ),
        sa.Column("stoichiometric_ratio", sa.Float(), nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    # Molecule relationships
    op.create_table(
        "molecule_relationships",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("workspace_id", sa.Uuid(), nullable=False, index=True),
        sa.Column(
            "source_molecule_id",
            sa.Uuid(),
            sa.ForeignKey("molecules.id"),
            nullable=False,
        ),
        sa.Column(
            "target_molecule_id",
            sa.Uuid(),
            sa.ForeignKey("molecules.id"),
            nullable=False,
        ),
        sa.Column("relationship_type", sa.String(50), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "source_molecule_id",
            "target_molecule_id",
            "relationship_type",
            name="uq_mol_rel",
        ),
    )


def downgrade() -> None:
    op.drop_table("molecule_relationships")
    op.drop_table("mixture_components")
    op.drop_table("molecule_identifiers")
    op.drop_table("molecules")
