"""Add run_import_templates table.

Workspace-scoped reusable column mappings for long-format run-file imports.

Revision ID: 016
Revises: 015
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "016"
down_revision = "015"


def upgrade() -> None:
    op.create_table(
        "run_import_templates",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("column_mapping", postgresql.JSONB(), nullable=False),
        sa.Column(
            "concentration_unit",
            sa.String(20),
            nullable=False,
            server_default="uM",
        ),
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
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_run_import_template_ws",
        "run_import_templates",
        ["workspace_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_run_import_template_ws", table_name="run_import_templates")
    op.drop_table("run_import_templates")
