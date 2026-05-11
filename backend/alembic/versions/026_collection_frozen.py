"""Add freeze + campaign-derivation columns to collections.

Lands the is_frozen flag plus a back-reference to the originating
campaign (derived_from_campaign_id). Frozen Collections are immutable
membership artifacts of a closed Screen Campaign — the domain guards
were added in Task 1.1 and the repository now round-trips both fields.

Pure additive — existing rows default to is_frozen=false / NULL
campaign id so no backfill is required.

Revision ID: 026_collection_frozen
Revises: 020_search_algorithms_overhaul
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "026_collection_frozen"
down_revision = "020_search_algorithms_overhaul"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "collections",
        sa.Column(
            "is_frozen",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "collections",
        sa.Column(
            "derived_from_campaign_id",
            sa.Uuid(as_uuid=True),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_collections_derived_from_campaign_id",
        "collections",
        ["derived_from_campaign_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_collections_derived_from_campaign_id", table_name="collections"
    )
    op.drop_column("collections", "derived_from_campaign_id")
    op.drop_column("collections", "is_frozen")
