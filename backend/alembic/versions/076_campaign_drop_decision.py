"""076 — drop the retired per-result decision columns.

``CampaignResult.decision`` (selected / deferred / rejected) and its
free-text ``decision_reason`` predate hit stages. Their only downstream
consumer — the auto-published "Hits" collection at close — was removed by
soft close (migration 075), leaving a second triage label that can
contradict the stage funnel. Stage outcomes plus per-stage manual
overrides (migration 074) express everything the decision did. The domain,
repository, and API stopped reading and writing both columns before this
migration; nothing selects them anymore. ``campaign_result.notes`` stays
and keeps its own edit path.

Dropped:
  * campaign_result.decision
  * campaign_result.decision_reason

Downgrade re-adds both columns with their original (pre-drop) definitions
so the schema matches, but their data is NOT restored — every row comes
back at the ``deferred`` default (or NULL for ``decision_reason``). Only
run downgrade to unblock a schema mismatch, not to recover prior values.

Revision ID: 076_campaign_drop_decision
Revises: 075_campaign_drop_hit_columns
Create Date: 2026-09-11
"""

from __future__ import annotations

from typing import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "076_campaign_drop_decision"
down_revision: str | None = "075_campaign_drop_hit_columns"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.drop_column("campaign_result", "decision")
    op.drop_column("campaign_result", "decision_reason")


def downgrade() -> None:
    op.add_column(
        "campaign_result",
        sa.Column("decision_reason", sa.Text(), nullable=True),
    )
    op.add_column(
        "campaign_result",
        sa.Column(
            "decision",
            sa.String(32),
            nullable=False,
            server_default="deferred",
        ),
    )
