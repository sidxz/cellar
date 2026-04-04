"""Bulk registration table.

Revision ID: 007
Revises: 006
Create Date: 2026-04-04
"""

import sqlalchemy as sa
from alembic import op

revision: str = "007"
down_revision: str = "006"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "bulk_registrations",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("workspace_id", sa.Uuid(), nullable=False, index=True),
        sa.Column("source_file", sa.String(500), nullable=False),
        sa.Column("file_format", sa.String(10), nullable=False),
        sa.Column("submitted_by", sa.Uuid(), nullable=False),
        sa.Column(
            "submitted_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "status",
            sa.String(30),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("total_count", sa.Integer(), nullable=False),
        sa.Column(
            "registered_count", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column(
            "duplicate_count", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column("error_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
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
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
    )

    op.create_index(
        "ix_bulk_reg_ws_status",
        "bulk_registrations",
        ["workspace_id", "status"],
    )


def downgrade() -> None:
    op.drop_index("ix_bulk_reg_ws_status", table_name="bulk_registrations")
    op.drop_table("bulk_registrations")
