"""061 — org_plate_policies (per-org plate loan/visibility policy).

Revision ID: 061_org_plate_policies
Revises: 060_add_owner_org_to_plates
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "061_org_plate_policies"
down_revision = "060_add_owner_org_to_plates"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "org_plate_policies",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("org_id", sa.Uuid(), nullable=False),
        sa.Column("require_approval", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column(
            "confirmation",
            sa.String(length=20),
            nullable=False,
            server_default="admin_confirm",
        ),
        sa.Column("default_due_days", sa.Integer(), nullable=True),
        sa.Column("plates_private", sa.Boolean(), nullable=False, server_default="false"),
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
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("workspace_id", "org_id", name="uq_org_plate_policy_ws_org"),
    )
    op.create_index(
        "ix_org_plate_policies_workspace_id", "org_plate_policies", ["workspace_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_org_plate_policies_workspace_id", table_name="org_plate_policies")
    op.drop_table("org_plate_policies")
