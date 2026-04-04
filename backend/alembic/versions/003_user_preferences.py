"""User preferences table for cross-device settings sync.

Revision ID: 003
Revises: 002
Create Date: 2026-04-03
"""

import sqlalchemy as sa
from alembic import op

revision: str = "003"
down_revision: str = "002"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "user_preferences",
        sa.Column("id", sa.Uuid(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("workspace_id", sa.Uuid(), nullable=False, index=True),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("preferences", sa.JSON(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("workspace_id", "user_id", name="uq_user_preferences_ws_user"),
    )


def downgrade() -> None:
    op.drop_table("user_preferences")
