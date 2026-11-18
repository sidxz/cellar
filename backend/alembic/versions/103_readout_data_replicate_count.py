"""103 — a summary-imported value records how many replicates it is the mean of.

One nullable column on ``readout_data``. Only well-less (summary) rows are given
a count; plate rows leave it null because their replicates are wells.

Revision ID: 103_readout_data_replicate_count
Revises: 102_melting_step_assignment
Create Date: 2026-11-17
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "103_readout_data_replicate_count"
down_revision = "102_melting_step_assignment"


def upgrade() -> None:
    op.add_column("readout_data", sa.Column("replicate_count", sa.Integer(), nullable=True))
    op.create_check_constraint(
        "ck_readout_data_replicates",
        "readout_data",
        "replicate_count IS NULL OR replicate_count >= 1",
    )


def downgrade() -> None:
    op.drop_constraint("ck_readout_data_replicates", "readout_data", type_="check")
    op.drop_column("readout_data", "replicate_count")
