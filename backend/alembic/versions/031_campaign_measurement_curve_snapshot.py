"""031 — campaign_measurement.curve_snapshot column.

Freezes the dose-response curve onto each CampaignMeasurement at import /
refresh time so a campaign cell's drawing is reproducible from the campaign
alone — even if the upstream `dose_response_curves` row is later refit.

Stored shape (only populated for source_kind=dose_response_curve):
    {
      "fitted_value": float,
      "top": float, "bottom": float, "hill_slope": float, "r_squared": float,
      "curve_class": str | null,
      "raw_data":        [{"x": float, "y": float}, ...],
      "excluded_points": [{"x": float, "y": float}, ...] | null
    }

Existing rows backfill to NULL; the frontend falls back to a live lookup
against `dose_response_curves` so pre-snapshot campaigns keep drawing. A
Refresh on a draft campaign re-runs the resolver which writes the snapshot,
upgrading the row in place. Closed campaigns keep their NULL snapshots
until they're reopened (out-of-scope here).

Revision ID: 031_cm_curve_snapshot
Revises: 030_cc_normalization
Create Date: 2026-05-12
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "031_cm_curve_snapshot"
down_revision: str | None = "030_cc_normalization"
branch_labels: None = None
depends_on: None = None


def upgrade() -> None:
    op.add_column(
        "campaign_measurement",
        sa.Column("curve_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("campaign_measurement", "curve_snapshot")
