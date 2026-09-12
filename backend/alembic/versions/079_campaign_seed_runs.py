"""079 — campaign.seed_runs (the runs a campaign was seeded from, spec D4).

Migration 078 scoped resolution to "the campaign's runs", derived as the union
of the RunRef run ids over its results' ``added_from``. That union is wrong:
a RunRef records only the run that WON the pick for that compound, so runs
whose values never won are dropped — a three-run mean collapsed to one run
on the next refresh/close, and "add run R3 + refresh existing cells" recorded
nothing and reverted.

The campaign now records its seed runs explicitly: every add-from-runs call
appends ``{run_id, protocol_id}`` for each run it imported from, whether or
not that run's values won. Resolution scopes each channel to the seed runs of
its own protocol; a protocol with no seed runs (a mirrored counter-screen)
resolves protocol-wide.

Added:
  * campaign.seed_runs — JSONB, NOT NULL, server_default '[]'. Backfilled from
    the distinct RunRef run ids over each campaign's results, joined to the
    run's protocol (ordered by run_date, id — insertion order is not
    recoverable). Campaigns with no run-attributed rows keep ``[]``.

Downgrade drops the column.

Revision ID: 079_campaign_seed_runs
Revises: 078_cc_resolve_from_all_runs
Create Date: 2026-09-11
"""

from __future__ import annotations

from typing import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "079_campaign_seed_runs"
down_revision: str | None = "078_cc_resolve_from_all_runs"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

# Exposed for the integration test (tests/integration/test_migration_079_seed_runs.py).
BACKFILL_SQL = """
UPDATE campaign c
   SET seed_runs = s.seed_runs
  FROM (
    SELECT r.campaign_id,
           jsonb_agg(
               jsonb_build_object('run_id', run.id, 'protocol_id', run.protocol_id)
               ORDER BY run.run_date, run.id
           ) AS seed_runs
      FROM (
        SELECT DISTINCT campaign_id, (added_from->>'run_id')::uuid AS run_id
          FROM campaign_result
         WHERE added_from->>'kind' = 'run'
      ) r
      JOIN runs run ON run.id = r.run_id
     GROUP BY r.campaign_id
  ) s
 WHERE c.id = s.campaign_id
"""


def upgrade() -> None:
    op.add_column(
        "campaign",
        sa.Column(
            "seed_runs",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.execute(BACKFILL_SQL)


def downgrade() -> None:
    op.drop_column("campaign", "seed_runs")
