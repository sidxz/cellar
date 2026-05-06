"""Add bulk_registration_items table + workflow_id index on bulk_registrations.

Per-row outcomes for bulk molecule registrations. Append-only child of the
BulkRegistration aggregate. Drives the per-row results table on the wizard's
Summary step (which compounds failed and why, what was deduped, etc).

Revision ID: 018
Revises: 017
"""

import sqlalchemy as sa
from alembic import op

revision = "018"
down_revision = "017"


def upgrade() -> None:
    op.create_table(
        "bulk_registration_items",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("bulk_registration_id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("row_index", sa.Integer(), nullable=False),
        sa.Column("action", sa.String(30), nullable=False),
        sa.Column("success", sa.Boolean(), nullable=False),
        sa.Column("molecule_id", sa.Uuid(), nullable=True),
        sa.Column("molecule_name", sa.String(500), nullable=True),
        sa.Column("registration_number", sa.String(50), nullable=True),
        sa.Column("batch_id", sa.Uuid(), nullable=True),
        sa.Column("batch_number", sa.String(50), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["bulk_registration_id"],
            ["bulk_registrations.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_bulk_reg_item_reg_action",
        "bulk_registration_items",
        ["bulk_registration_id", "action"],
    )
    op.create_index(
        "ix_bulk_reg_item_reg_row",
        "bulk_registration_items",
        ["bulk_registration_id", "row_index"],
        unique=True,
    )
    op.create_index(
        "ix_bulk_reg_workflow_id",
        "bulk_registrations",
        ["workspace_id", "workflow_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_bulk_reg_workflow_id", table_name="bulk_registrations")
    op.drop_index("ix_bulk_reg_item_reg_row", table_name="bulk_registration_items")
    op.drop_index("ix_bulk_reg_item_reg_action", table_name="bulk_registration_items")
    op.drop_table("bulk_registration_items")
