"""Synthesis routes — SynthesisRoute aggregate + ReactionStep owned entity.

Revision ID: 012
Revises: 011
Create Date: 2026-04-05
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "012"
down_revision = "011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "synthesis_routes",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", UUID(as_uuid=True), nullable=False, index=True),
        sa.Column(
            "target_molecule_id",
            UUID(as_uuid=True),
            sa.ForeignKey("molecules.id"),
            nullable=False,
            index=True,
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text),
        sa.Column("route_type", sa.String(30), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, index=True),
        sa.Column("total_steps", sa.Integer, nullable=False, server_default="0"),
        sa.Column("overall_yield", sa.Float),
        sa.Column("estimated_cost_value", sa.Float),
        sa.Column("estimated_cost_unit", sa.String(30)),
        sa.Column("scale", sa.String(30)),
        sa.Column("source", sa.String(50), nullable=False),
        sa.Column("source_reference", sa.Text),
        sa.Column("created_by", UUID(as_uuid=True), nullable=False),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
    )

    # Partial unique: at most one PREFERRED route per target molecule
    op.create_index(
        "ix_synth_route_preferred_unique",
        "synthesis_routes",
        ["target_molecule_id"],
        unique=True,
        postgresql_where=sa.text("status = 'preferred'"),
    )

    op.create_table(
        "reaction_steps",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "route_id",
            UUID(as_uuid=True),
            sa.ForeignKey("synthesis_routes.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("step_number", sa.Integer, nullable=False),
        sa.Column("branch_label", sa.String(50)),
        sa.Column("name", sa.String(255)),
        sa.Column("named_reaction", sa.String(255)),
        sa.Column("reaction_smiles", sa.Text),
        sa.Column("reaction_smarts", sa.Text),
        sa.Column("product_molecule_id", UUID(as_uuid=True)),
        sa.Column("product_description", sa.Text),
        # ReactionConditions VO (flattened)
        sa.Column("condition_solvent", sa.String(255)),
        sa.Column("condition_temperature", sa.String(100)),
        sa.Column("condition_pressure", sa.String(100)),
        sa.Column("condition_catalyst", sa.String(255)),
        sa.Column("condition_atmosphere", sa.String(100)),
        sa.Column("condition_time", sa.String(100)),
        sa.Column("condition_additional", JSONB),
        # ReactionOutcome VO (flattened)
        sa.Column("outcome_yield_percent", sa.Float),
        sa.Column("outcome_crude_yield_percent", sa.Float),
        sa.Column("outcome_purity_percent", sa.Float),
        sa.Column("outcome_actual_scale_value", sa.Float),
        sa.Column("outcome_actual_scale_unit", sa.String(30)),
        sa.Column("outcome_purification_method", sa.String(255)),
        # Reagents as JSONB list
        sa.Column("reagents", JSONB, server_default="[]"),
        # DAG edges
        sa.Column("preceding_step_ids", JSONB, server_default="[]"),
        # Cross-context references
        sa.Column("eln_entry_id", UUID(as_uuid=True)),
        sa.Column("batch_id", UUID(as_uuid=True)),
        sa.Column("notes", sa.Text),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
    )


def downgrade() -> None:
    op.drop_table("reaction_steps")
    op.drop_index("ix_synth_route_preferred_unique", table_name="synthesis_routes")
    op.drop_table("synthesis_routes")
