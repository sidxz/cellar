"""077 — campaign_stage.kind (criteria | manual).

Hit stages so far were always a named AND of numeric criteria over the
campaign's channels. A *manual* stage has no criteria at all: every compound
in its population sits at the new ``pending`` outcome until a chemist
promotes it (stage override -> hit) or demotes it (override -> miss).
Children of a manual stage take its hits as their population, exactly as for
a criteria stage. Outcomes are computed, never stored, so nothing but the
discriminator needs persisting.

Added:
  * campaign_stage.kind — String(16), NOT NULL, server_default 'criteria'.
    Existing rows backfill to 'criteria' via the default, which is the
    behaviour they already had.

Downgrade drops the column; every stage reverts to criteria evaluation and
any manual stage's compounds fall back to the AND of its (empty) criteria —
i.e. they all read as hits. Only run downgrade to unblock a schema mismatch.

Revision ID: 077_campaign_stage_kind
Revises: 076_campaign_drop_decision
Create Date: 2026-09-11
"""

from __future__ import annotations

from typing import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "077_campaign_stage_kind"
down_revision: str | None = "076_campaign_drop_decision"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "campaign_stage",
        sa.Column("kind", sa.String(16), nullable=False, server_default="criteria"),
    )


def downgrade() -> None:
    op.drop_column("campaign_stage", "kind")
