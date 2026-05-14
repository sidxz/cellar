"""034 — dose_response_curves.dose_response_config_snapshot column.

Freezes the DR config that drove each fit (curve_type, y_normalization,
x_readout_name, fit bounds) onto the curve row so a future config edit
on the readout-def doesn't silently re-interpret historical curves.

Same principle as ``campaign_measurement.curve_snapshot`` (mig 031)
one level deeper — the curve row becomes reproducible from its own
fields rather than depending on a join to the readout-def's *current*
config.

Null on existing rows; the fitter starts populating it after this
migration. Readers fall back to the readout-def's live config when the
snapshot is missing.

Revision ID: 034_drc_config_snapshot
Revises: 033_drc_readout_definition_id
Create Date: 2026-05-14
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "034_drc_config_snapshot"
down_revision: str | None = "033_drc_readout_definition_id"
branch_labels: None = None
depends_on: None = None


def upgrade() -> None:
    op.add_column(
        "dose_response_curves",
        sa.Column(
            "dose_response_config_snapshot",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("dose_response_curves", "dose_response_config_snapshot")
