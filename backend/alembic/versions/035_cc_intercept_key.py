"""035 — campaign_channel.intercept_key top-level column.

Decouples a campaign channel's intercept identity (which DR intercept it
surfaces — primary EC50 vs. secondary EC90) from its hit threshold. Before
this, identity was implicitly carried inside ``hit_threshold.intercept_key``;
a channel with no threshold (display-only column) lost its intercept
identity on the wire, collapsing EC90 cells onto the EC50 channel_key.

JSONB column, nullable. NULL means the channel targets the curve's primary
intercept (matches today's behavior for every existing campaign channel,
so no backfill is required — legacy reads fall through cleanly).

Revision ID: 035_cc_intercept_key
Revises: 034_drc_config_snapshot
Create Date: 2026-05-14
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "035_cc_intercept_key"
down_revision: str | None = "034_drc_config_snapshot"
branch_labels: None = None
depends_on: None = None


def upgrade() -> None:
    op.add_column(
        "campaign_channel",
        sa.Column(
            "intercept_key",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("campaign_channel", "intercept_key")
