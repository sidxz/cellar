"""one spelling per unit on readouts, conditions and form templates

Revision ID: 088_canonical_units
Revises: 087_campaign_name_snapshot_width
Create Date: 2026-10-08
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

from cellar.infrastructure.persistence.unit_rewrite import rewrite_stored_units

revision: str = "088_canonical_units"
down_revision: str | None = "087_campaign_name_snapshot_width"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    rewrite_stored_units(op.get_bind())


def downgrade() -> None:
    # Spelling only; the old variants carry nothing worth restoring.
    pass
