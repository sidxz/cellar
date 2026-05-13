"""Add cdd_plate_imports and cdd_plate_sync tables.

Revision ID: 013
Revises: 012
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "013"
down_revision = "012"


def upgrade() -> None:
    # -- cdd_plate_imports: tracking table for plate import operations
    op.create_table(
        "cdd_plate_imports",
        sa.Column(
            "id",
            sa.Uuid(),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("workspace_id", sa.Uuid(), nullable=False, index=True),
        sa.Column("cdd_vault_id", sa.String(50), nullable=False),
        sa.Column(
            "status",
            sa.String(30),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("workflow_id", sa.String(255), nullable=True),
        sa.Column("total_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("plates_registered", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("plates_duplicate", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("plates_error", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("wells_mapped", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("wells_unresolved", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_processed_offset", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("submitted_by", sa.Uuid(), nullable=False),
        sa.Column(
            "submitted_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
    )
    op.create_index(
        "ix_cdd_plate_import_ws_status",
        "cdd_plate_imports",
        ["workspace_id", "status"],
    )

    # -- cdd_plate_sync: CDD plate ID -> internal plate ID mapping
    op.create_table(
        "cdd_plate_sync",
        sa.Column(
            "id",
            sa.Uuid(),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("workspace_id", sa.Uuid(), nullable=False, index=True),
        sa.Column("cdd_vault_id", sa.String(50), nullable=False),
        sa.Column("cdd_plate_id", sa.Integer(), nullable=False),
        sa.Column("plate_id", sa.Uuid(), nullable=False),
        sa.Column("cdd_statistics", JSONB(), nullable=True),
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
    op.create_index(
        "uq_cdd_plate_sync_ws_vault_plate",
        "cdd_plate_sync",
        ["workspace_id", "cdd_vault_id", "cdd_plate_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_cdd_plate_sync_ws_vault_plate", table_name="cdd_plate_sync")
    op.drop_table("cdd_plate_sync")
    op.drop_index("ix_cdd_plate_import_ws_status", table_name="cdd_plate_imports")
    op.drop_table("cdd_plate_imports")
