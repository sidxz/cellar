"""057 — rgroup_decomposition_runs + rgroup_assignments.

Persisted RGroupDecompositionRun aggregate. The run header doubles as a
(membership_hash, core_hash) cache via a partial index WHERE status='ready'.
Assignments are queryable rows (not a JSONB blob) so a large decomposition can
be paginated/aggregated.

Revision ID: 057_rgroup_decomposition_runs
Revises: 056_run_hit_criteria
Create Date: 2026-06-11
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "057_rgroup_decomposition_runs"
down_revision: str | None = "056_run_hit_criteria"
branch_labels: None = None
depends_on: None = None


def upgrade() -> None:
    op.create_table(
        "rgroup_decomposition_runs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("requested_by", sa.Uuid(), nullable=False),
        sa.Column("membership_hash", sa.Text(), nullable=False),
        sa.Column("core_smiles", sa.Text(), nullable=False),
        sa.Column("core_hash", sa.Text(), nullable=False),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("rgroup_labels", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("matched_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("unmatched_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
    )
    op.create_index(
        "rgroup_runs_workspace_status",
        "rgroup_decomposition_runs",
        ["workspace_id", "status"],
    )
    op.create_index(
        "rgroup_runs_cache",
        "rgroup_decomposition_runs",
        ["membership_hash", "core_hash", sa.text("completed_at DESC")],
        postgresql_where=sa.text("status = 'ready'"),
    )

    op.create_table(
        "rgroup_assignments",
        sa.Column(
            "run_id",
            sa.Uuid(),
            sa.ForeignKey("rgroup_decomposition_runs.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("molecule_id", sa.Uuid(), primary_key=True),
        sa.Column("rgroups", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("rgroup_assignments")
    op.drop_index("rgroup_runs_cache", table_name="rgroup_decomposition_runs")
    op.drop_index("rgroup_runs_workspace_status", table_name="rgroup_decomposition_runs")
    op.drop_table("rgroup_decomposition_runs")
