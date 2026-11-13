"""well note: free-text bench observation per run position

Revision ID: 094_well_note
Revises: 093_instrument_curves
Create Date: 2026-11-12
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "094_well_note"
down_revision: str | None = "093_instrument_curves"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("wells", sa.Column("note", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("wells", "note")
