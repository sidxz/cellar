"""collection type attribute

Adds a ``type`` column to ``collections`` categorizing each collection by its
role in the screening cascade (generic | reference_set | library | hit_list |
series | distribution_set). Existing rows backfill to ``generic`` via the
server default.

Revision ID: 052_collection_type
Revises: 051_protocol_run_targets_m2m
Create Date: 2026-06-05
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "052_collection_type"
down_revision = "051_protocol_run_targets_m2m"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "collections",
        sa.Column(
            "type",
            sa.String(length=32),
            nullable=False,
            server_default="generic",
        ),
    )


def downgrade() -> None:
    op.drop_column("collections", "type")
