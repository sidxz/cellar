"""054 — favorites table.

Per-user, workspace-scoped bookmarks of any entity. Polymorphic by design:
``entity_type`` + ``entity_id`` is a soft reference (no FK) so the
Personalization context stays decoupled from the favorited entity's context.

Revision ID: 054_favorites
Revises: 053_target_link_restrict
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "054_favorites"
down_revision = "053_target_link_restrict"


def upgrade() -> None:
    op.create_table(
        "favorites",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("entity_type", sa.String(50), nullable=False),
        sa.Column("entity_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_favorites_ws_user_entity",
        "favorites",
        ["workspace_id", "user_id", "entity_type", "entity_id"],
        unique=True,
    )
    op.create_index("ix_favorites_workspace_id", "favorites", ["workspace_id"])


def downgrade() -> None:
    op.drop_index("ix_favorites_workspace_id", table_name="favorites")
    op.drop_index("uq_favorites_ws_user_entity", table_name="favorites")
    op.drop_table("favorites")
