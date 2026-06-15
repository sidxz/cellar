"""058 — sar_activity_projections + sar_activity_values.

Persisted SarActivityProjection aggregate (one materialized scalar per molecule
for a color channel). The header doubles as a (membership_hash, channel_hash)
cache via a partial index WHERE status='ready'. Values are SPARSE — only
molecules with a value — so a LEFT JOIN nulls render as heatmap gaps / uncolored
cells, exactly as the client did pre-Part-2. Core-independent: reused across
decomposition runs of the same membership.

Revision ID: 058_sar_activity_projections
Revises: 057_rgroup_decomposition_runs
Create Date: 2026-06-15
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "058_sar_activity_projections"
down_revision: str | None = "057_rgroup_decomposition_runs"
branch_labels: None = None
depends_on: None = None


def upgrade() -> None:
    op.create_table(
        "sar_activity_projections",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("requested_by", sa.Uuid(), nullable=False),
        sa.Column("membership_hash", sa.Text(), nullable=False),
        sa.Column("channel_hash", sa.Text(), nullable=False),
        sa.Column("channel_spec", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("value_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
    )
    op.create_index(
        "sar_activity_proj_workspace_status",
        "sar_activity_projections",
        ["workspace_id", "status"],
    )
    op.create_index(
        "sar_activity_proj_cache",
        "sar_activity_projections",
        ["membership_hash", "channel_hash", sa.text("completed_at DESC")],
        postgresql_where=sa.text("status = 'ready'"),
    )

    op.create_table(
        "sar_activity_values",
        sa.Column(
            "projection_id",
            sa.Uuid(),
            sa.ForeignKey("sar_activity_projections.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("molecule_id", sa.Uuid(), primary_key=True),
        sa.Column("scalar", sa.Float(), nullable=False),
        sa.Column("unit", sa.Text(), nullable=True),
        sa.Column("qualifier", sa.Text(), nullable=True),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("sar_activity_values")
    op.drop_index("sar_activity_proj_cache", table_name="sar_activity_projections")
    op.drop_index("sar_activity_proj_workspace_status", table_name="sar_activity_projections")
    op.drop_table("sar_activity_projections")
