"""measured curve x label: name of the x quantity per channel

Revision ID: 095_measured_curve_x_label
Revises: 094_well_note
Create Date: 2026-11-12
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "095_measured_curve_x_label"
down_revision: str | None = "094_well_note"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("measured_curves", sa.Column("x_label", sa.String(100), nullable=True))


def downgrade() -> None:
    op.drop_column("measured_curves", "x_label")
