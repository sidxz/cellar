"""condition definitions carry the value that defines the protocol (Hypoxia: yes, 72 h)

Revision ID: 091_condition_fixed_value
Revises: 090_canonical_units_again
Create Date: 2026-10-08

Nullable and not backfilled: existing conditions (locked protocols included) keep varying per
run until someone fixes their value.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "091_condition_fixed_value"
down_revision: str | None = "090_canonical_units_again"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("condition_definitions", sa.Column("fixed_value", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("condition_definitions", "fixed_value")
