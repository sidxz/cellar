"""run-collection M2M

A run can attach one or more collections (libraries); the protocol shows
rolled-up screening coverage over the runs that attached each collection. Pure
association table, mirroring ``run_targets`` (migration 051) but with the
referenced (collection) side declared ``RESTRICT`` from the start — a collection
referenced by a run cannot be silently deleted (the lesson of migration 053).
The owner (run) side keeps CASCADE: deleting a run drops its link rows.

Revision ID: 055_run_collections_m2m
Revises: 054_favorites
Create Date: 2026-06-07
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "055_run_collections_m2m"
down_revision = "054_favorites"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "run_collections",
        sa.Column(
            "run_id",
            sa.Uuid(),
            sa.ForeignKey("runs.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "collection_id",
            sa.Uuid(),
            sa.ForeignKey("collections.id", ondelete="RESTRICT"),
            primary_key=True,
        ),
    )
    op.create_index("ix_run_collections_collection", "run_collections", ["collection_id"])


def downgrade() -> None:
    op.drop_index("ix_run_collections_collection", table_name="run_collections")
    op.drop_table("run_collections")
