"""028 — per-result source attribution.

Drop campaign.compound_source (single-source-at-create model removed).
Add campaign_result.added_from (nullable JSONB — per-result provenance).

Pre-MVP: no data migration needed.

Revision ID: 028_per_result_added_from
Revises: 027_screen_campaign
Create Date: 2026-05-11
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "028_per_result_added_from"
down_revision: str | None = "027_screen_campaign"
branch_labels: None = None
depends_on: None = None


def upgrade() -> None:
    # Drop the campaign-level compound_source JSONB column.
    op.drop_column("campaign", "compound_source")

    # Add per-result source attribution (nullable — None means manual/no attribution).
    op.add_column(
        "campaign_result",
        sa.Column(
            "added_from",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("campaign_result", "added_from")

    # Restore as nullable — we cannot recover the lost data.
    op.add_column(
        "campaign",
        sa.Column(
            "compound_source",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )
