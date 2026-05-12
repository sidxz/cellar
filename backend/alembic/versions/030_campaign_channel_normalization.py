"""030 — campaign_channel.normalization_applied column.

Picks which ``normalization_applied`` layer a readout_data channel reads
from. NULL means the raw layer (matches the historical reuse key). Set to
"percent_inhibition", "z_score", etc. to select a computed layer instead.

Existing rows backfill to NULL, which preserves their current semantics
(raw layer is what they were resolving to before this column existed —
the channel-resolution query did not filter on normalization_applied).

Revision ID: 030_cc_normalization
Revises: 029_cm_audit_snapshot
Create Date: 2026-05-12
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "030_cc_normalization"
down_revision: str | None = "029_cm_audit_snapshot"
branch_labels: None = None
depends_on: None = None


def upgrade() -> None:
    op.add_column(
        "campaign_channel",
        sa.Column("normalization_applied", sa.String(length=32), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("campaign_channel", "normalization_applied")
