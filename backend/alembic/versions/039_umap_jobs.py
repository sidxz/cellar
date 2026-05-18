"""039 — umap_jobs table.

Persisted UmapJob aggregate for V3 cluster map. result_json doubles as the
Postgres-backed cache; partial index on (ids_hash, picker, picker_param_hash,
completed_at) WHERE status='ready' serves the 1-hour TTL lookup.

Revision ID: 039_umap_jobs
Revises: 038_scaffold_tree_jobs
Create Date: 2026-05-18
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "039_umap_jobs"
down_revision: str | None = "038_scaffold_tree_jobs"
branch_labels: None = None
depends_on: None = None


def upgrade() -> None:
    op.create_table(
        "umap_jobs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("requested_by", sa.Uuid(), nullable=False),
        sa.Column("ids_hash", sa.Text(), nullable=False),
        sa.Column("picker", sa.String(20), nullable=False),
        sa.Column(
            "picker_params",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
        sa.Column("picker_param_hash", sa.Text(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column(
            "result_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.CheckConstraint(
            "picker IN ('maxmin', 'butina')",
            name="umap_jobs_picker_check",
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'running', 'ready', 'failed', 'cancelled')",
            name="umap_jobs_status_check",
        ),
    )
    op.create_index(
        "umap_jobs_cache",
        "umap_jobs",
        ["ids_hash", "picker", "picker_param_hash", sa.text("completed_at DESC")],
        postgresql_where=sa.text("status = 'ready'"),
    )
    op.create_index(
        "umap_jobs_workspace",
        "umap_jobs",
        ["workspace_id", sa.text("requested_at DESC")],
    )


def downgrade() -> None:
    op.drop_index("umap_jobs_workspace", table_name="umap_jobs")
    op.drop_index("umap_jobs_cache", table_name="umap_jobs")
    op.drop_table("umap_jobs")
