"""Add protocol_projects table, is_computed column, and performance indexes.

Revision ID: 022
Revises: 021
"""

from alembic import op
import sqlalchemy as sa

revision = "022"
down_revision = "021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- protocol_projects join table ---
    op.create_table(
        "protocol_projects",
        sa.Column("protocol_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["protocol_id"],
            ["protocols.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("protocol_id", "project_id"),
    )
    op.create_index(
        "ix_protocol_projects_project",
        "protocol_projects",
        ["project_id"],
    )

    # --- readout_data: composite index for computation queries ---
    op.create_index(
        "ix_readout_data_run_def",
        "readout_data",
        ["run_id", "readout_definition_id"],
    )

    # --- readout_data: is_computed flag ---
    op.add_column(
        "readout_data",
        sa.Column(
            "is_computed",
            sa.Boolean(),
            server_default="false",
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("readout_data", "is_computed")
    op.drop_index("ix_readout_data_run_def", table_name="readout_data")
    op.drop_index("ix_protocol_projects_project", table_name="protocol_projects")
    op.drop_table("protocol_projects")
