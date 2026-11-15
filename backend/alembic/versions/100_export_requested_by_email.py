"""100 — export_jobs.requested_by_email.

Who asked for an export, as their email read when they asked: the PDF, Excel and
SDF files print it beside the export time. Null on jobs from before.

Revision ID: 100_export_requested_by_email
Revises: 099_recent_searches
Create Date: 2026-11-15
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "100_export_requested_by_email"
down_revision = "099_recent_searches"


def upgrade() -> None:
    op.add_column("export_jobs", sa.Column("requested_by_email", sa.String(320), nullable=True))


def downgrade() -> None:
    op.drop_column("export_jobs", "requested_by_email")
