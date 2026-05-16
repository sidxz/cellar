"""036 — export_jobs table.

Persisted ExportJob aggregate. Status / progress columns are mutated by
the worker; query_snapshot is the audit-trail evidence of what was asked.
The (status, expires_at) index supports the nightly purge sweep.

Revision ID: 036_export_jobs
Revises: 035_cc_intercept_key
Create Date: 2026-05-16
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "036_export_jobs"
down_revision: str | None = "035_cc_intercept_key"
branch_labels: None = None
depends_on: None = None


def upgrade() -> None:
    op.create_table(
        "export_jobs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("requested_by", sa.Uuid(), nullable=False),
        sa.Column("source", sa.String(50), nullable=False),
        sa.Column("format", sa.String(10), nullable=False),
        sa.Column("query_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("row_count", sa.Integer(), nullable=True),
        sa.Column("progress", sa.Float(), nullable=True),
        sa.Column("file_key", sa.String(1024), nullable=True),
        sa.Column("byte_size", sa.BigInteger(), nullable=True),
        sa.Column("content_type", sa.String(255), nullable=True),
        sa.Column("filename", sa.String(512), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_index(
        "ix_export_jobs_workspace_requested_at",
        "export_jobs",
        ["workspace_id", sa.text("requested_at DESC")],
    )
    op.create_index(
        "ix_export_jobs_status_expires_at",
        "export_jobs",
        ["status", "expires_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_export_jobs_status_expires_at", table_name="export_jobs")
    op.drop_index("ix_export_jobs_workspace_requested_at", table_name="export_jobs")
    op.drop_table("export_jobs")
