"""078 — campaign_channel.resolve_from_all_runs (per-readout run-scope opt-out).

A campaign seeded from protocol runs now resolves every channel against only
those runs: the campaign's run scope is the union of the RunRef run ids over
its results' ``added_from`` (spec D4). Before this, resolution swept every run
of the protocol, so a later unrelated run could silently move a closed-looking
campaign's numbers.

Some readouts genuinely belong outside that scope — a counter-screen, solubility
or a physchem endpoint measured whenever, not in the campaign's own screening
runs. ``resolve_from_all_runs`` is that per-channel opt-out: set, the channel
resolves protocol-wide exactly as before.

Added:
  * campaign_channel.resolve_from_all_runs — Boolean, NOT NULL, server_default
    false. Existing rows backfill to false (run-scoped), which is the intended
    new behaviour; a campaign with no run sources is unrestricted anyway, so
    only run-seeded campaigns change.

Downgrade drops the column; every channel reverts to protocol-wide resolution.

Revision ID: 078_cc_resolve_from_all_runs
Revises: 077_campaign_stage_kind
Create Date: 2026-09-11
"""

from __future__ import annotations

from typing import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "078_cc_resolve_from_all_runs"
down_revision: str | None = "077_campaign_stage_kind"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "campaign_channel",
        sa.Column(
            "resolve_from_all_runs",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    op.drop_column("campaign_channel", "resolve_from_all_runs")
