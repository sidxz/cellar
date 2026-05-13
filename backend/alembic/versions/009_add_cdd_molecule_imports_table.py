"""Add cdd_molecule_imports table for CDD vault molecule import tracking.

Revision ID: 009
Revises: 008
"""

import sqlalchemy as sa
from alembic import op

revision = "009"
down_revision = "008"


def upgrade() -> None:
    op.create_table(
        "cdd_molecule_imports",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("workspace_id", sa.Uuid(), nullable=False, index=True),
        sa.Column("cdd_vault_id", sa.String(50), nullable=False),
        sa.Column("import_mode", sa.String(30), nullable=False),
        sa.Column("originating_org_id", sa.Uuid(), sa.ForeignKey("organizations.id"), nullable=True),
        sa.Column("filter_criteria", sa.dialects.postgresql.JSONB(), nullable=True),
        sa.Column("status", sa.String(30), nullable=False, server_default="pending"),
        sa.Column("workflow_id", sa.String(255), nullable=True),
        sa.Column("total_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("registered_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("duplicate_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("skipped_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_processed_offset", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("submitted_by", sa.Uuid(), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
    )
    op.create_index(
        "ix_cdd_mol_import_ws_status",
        "cdd_molecule_imports",
        ["workspace_id", "status"],
    )


def downgrade() -> None:
    op.drop_index("ix_cdd_mol_import_ws_status", table_name="cdd_molecule_imports")
    op.drop_table("cdd_molecule_imports")
