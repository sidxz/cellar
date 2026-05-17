"""038 — scaffold_tree_jobs table.

Persisted ScaffoldTreeJob aggregate. result_json doubles as the
Postgres-backed cache; partial index on (ids_hash, completed_at)
WHERE status='ready' serves the 1-hour TTL lookup.

Revision ID: 038_scaffold_tree_jobs
Revises: 037_bemis_murcko_smiles
Create Date: 2026-05-17
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "038_scaffold_tree_jobs"
down_revision: str | None = "037_bemis_murcko_smiles"
branch_labels: None = None
depends_on: None = None


def upgrade() -> None:
    op.create_table(
        "scaffold_tree_jobs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("requested_by", sa.Uuid(), nullable=False),
        sa.Column("ids_hash", sa.Text(), nullable=False),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("result_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
    )
    op.create_index(
        "scaffold_tree_jobs_workspace_status",
        "scaffold_tree_jobs",
        ["workspace_id", "status"],
    )
    op.create_index(
        "scaffold_tree_jobs_requested_by_at",
        "scaffold_tree_jobs",
        ["requested_by", sa.text("requested_at DESC")],
    )
    op.create_index(
        "scaffold_tree_jobs_cache",
        "scaffold_tree_jobs",
        ["ids_hash", sa.text("completed_at DESC")],
        postgresql_where=sa.text("status = 'ready'"),
    )


def downgrade() -> None:
    op.drop_index("scaffold_tree_jobs_cache", table_name="scaffold_tree_jobs")
    op.drop_index("scaffold_tree_jobs_requested_by_at", table_name="scaffold_tree_jobs")
    op.drop_index("scaffold_tree_jobs_workspace_status", table_name="scaffold_tree_jobs")
    op.drop_table("scaffold_tree_jobs")
