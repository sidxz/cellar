"""075 — drop the retired per-channel/per-cell hit columns and campaign
publish/signature columns.

The channel-level hit threshold and per-measurement hit call were replaced
by campaign_stage / campaign_stage_override (migration 074): a stage now
evaluates hits from a named set of criteria over one or more channels,
computed on read rather than stored per cell. The campaign-level publish
flow (``publishes_collection``, ``published_collection_id``, and the
close-time ``signature_id``) was replaced by soft close (status +
closed_at/closed_by/close_note) with no collection publish step. The
domain, repository, and API stopped reading and writing all five columns
before this migration; nothing selects them anymore.

Dropped:
  * campaign_channel.hit_threshold
  * campaign_measurement.hit_call
  * campaign.signature_id
  * campaign.publishes_collection
  * campaign.published_collection_id

Downgrade re-adds all five columns with their original (pre-drop)
definitions so the schema matches, but their data is NOT restored — every
row comes back NULL (or, for ``publishes_collection``, the column's own
``true`` default, since it was NOT NULL). Anything dropped by an upgrade
of this migration is gone; only run downgrade to unblock a schema
mismatch, not to recover prior values.

Revision ID: 075_campaign_drop_hit_columns
Revises: 074_campaign_hit_stages
Create Date: 2026-09-11
"""

from __future__ import annotations

from typing import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "075_campaign_drop_hit_columns"
down_revision: str | None = "074_campaign_hit_stages"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.drop_column("campaign_channel", "hit_threshold")
    op.drop_column("campaign_measurement", "hit_call")
    op.drop_column("campaign", "signature_id")
    op.drop_column("campaign", "publishes_collection")
    op.drop_column("campaign", "published_collection_id")


def downgrade() -> None:
    op.add_column(
        "campaign",
        sa.Column("published_collection_id", sa.Uuid(as_uuid=True), nullable=True),
    )
    op.add_column(
        "campaign",
        sa.Column(
            "publishes_collection",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
    )
    op.add_column(
        "campaign",
        sa.Column("signature_id", sa.Uuid(as_uuid=True), nullable=True),
    )
    op.add_column(
        "campaign_measurement",
        sa.Column("hit_call", sa.String(16), nullable=True),
    )
    op.add_column(
        "campaign_channel",
        sa.Column("hit_threshold", postgresql.JSONB(), nullable=True),
    )
