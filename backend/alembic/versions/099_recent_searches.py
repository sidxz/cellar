"""099 — recent_searches table.

Each user's own search history per workspace: one row per distinct search
(``query_key``, the query without its aggregation rule), newest ``ran_at``
wins, trimmed to the newest few by the repository. ``query`` / ``columns``
have the shape ``saved_searches`` stores.

Revision ID: 099_recent_searches
Revises: 098_rename_latest_run_rule
Create Date: 2026-11-14
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "099_recent_searches"
down_revision = "098_rename_latest_run_rule"


def upgrade() -> None:
    op.create_table(
        "recent_searches",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("query_key", sa.String(64), nullable=False),
        sa.Column("query", JSONB(), nullable=False),
        sa.Column("columns", JSONB(), nullable=True),
        sa.Column("result_count", sa.Integer(), nullable=True),
        sa.Column("ran_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_recent_searches_ws_user_key",
        "recent_searches",
        ["workspace_id", "user_id", "query_key"],
        unique=True,
    )
    op.create_index(
        "ix_recent_searches_ws_user_ran",
        "recent_searches",
        ["workspace_id", "user_id", "ran_at"],
    )
    op.create_index("ix_recent_searches_workspace_id", "recent_searches", ["workspace_id"])


def downgrade() -> None:
    op.drop_index("ix_recent_searches_workspace_id", table_name="recent_searches")
    op.drop_index("ix_recent_searches_ws_user_ran", table_name="recent_searches")
    op.drop_index("uq_recent_searches_ws_user_key", table_name="recent_searches")
    op.drop_table("recent_searches")
