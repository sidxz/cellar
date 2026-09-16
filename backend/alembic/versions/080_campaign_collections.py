"""campaign-collection M2M (the libraries a campaign screened)

The campaign twin of ``run_collections`` (migration 055). A campaign names the
libraries it screened; coverage — how many of a library's members got a reading
in any of the campaign's seed runs — is computed live, never stored.

Same FK discipline as 055: the owner (campaign) side CASCADEs so deleting a
campaign drops its link rows, the referenced (collection) side is RESTRICT so a
library a campaign points at cannot be silently deleted.

Revision ID: 080_campaign_collections
Revises: 079_campaign_seed_runs
Create Date: 2026-09-14
"""

from __future__ import annotations

from typing import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "080_campaign_collections"
down_revision: str | None = "079_campaign_seed_runs"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "campaign_collections",
        sa.Column(
            "campaign_id",
            sa.Uuid(),
            sa.ForeignKey("campaign.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "collection_id",
            sa.Uuid(),
            sa.ForeignKey("collections.id", ondelete="RESTRICT"),
            primary_key=True,
        ),
    )
    op.create_index(
        "ix_campaign_collections_collection", "campaign_collections", ["collection_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_campaign_collections_collection", table_name="campaign_collections")
    op.drop_table("campaign_collections")
