"""029 — campaign_measurement audit + snapshot columns.

Adds report-grade fields to each CampaignMeasurement:
- override_reason         (B8 audit defensibility)
- test_concentration_*    (B6 snapshot — at what concentration was the value measured)
- replicate_count         (B6 snapshot — N runs that contributed to selection_rule)
- qc_pass                 (B6 snapshot — did source data pass QC at import time)
- contributing_run_ids    (B6 snapshot — which runs fed the selection rule)

All nullable. Existing closed campaigns keep null values for these fields and
remain valid. DAIKON serializer emits null when absent (flat schema).

Revision ID: 029_cm_audit_snapshot
Revises: 028_per_result_added_from
Create Date: 2026-05-11
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "029_cm_audit_snapshot"
down_revision: str | None = "028_per_result_added_from"
branch_labels: None = None
depends_on: None = None


def upgrade() -> None:
    op.add_column(
        "campaign_measurement",
        sa.Column("override_reason", sa.Text(), nullable=True),
    )
    op.add_column(
        "campaign_measurement",
        sa.Column("test_concentration_value", sa.Float(), nullable=True),
    )
    op.add_column(
        "campaign_measurement",
        sa.Column("test_concentration_unit", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "campaign_measurement",
        sa.Column("replicate_count", sa.Integer(), nullable=True),
    )
    op.add_column(
        "campaign_measurement",
        sa.Column("qc_pass", sa.Boolean(), nullable=True),
    )
    op.add_column(
        "campaign_measurement",
        sa.Column(
            "contributing_run_ids",
            postgresql.ARRAY(postgresql.UUID(as_uuid=True)),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("campaign_measurement", "contributing_run_ids")
    op.drop_column("campaign_measurement", "qc_pass")
    op.drop_column("campaign_measurement", "replicate_count")
    op.drop_column("campaign_measurement", "test_concentration_unit")
    op.drop_column("campaign_measurement", "test_concentration_value")
    op.drop_column("campaign_measurement", "override_reason")
