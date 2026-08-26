"""065 — targets mirror columns (spec 2026-08-24-targets-from-prot-cellar)

``targets`` becomes a read-only mirror of prot-cellar's catalog. Two
nullable columns: ``chembl_id`` (carried from the source) and
``source_version`` (prot-cellar's optimistic-concurrency counter — the
re-sync change signal; NULL marks a pre-mirror, locally-created row).

Revision ID: 065_target_mirror_columns
Revises: 064_kiosk_devices
"""

import sqlalchemy as sa
from alembic import op

revision = "065_target_mirror_columns"
down_revision = "064_kiosk_devices"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("targets", sa.Column("chembl_id", sa.String(30), nullable=True))
    op.add_column("targets", sa.Column("source_version", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("targets", "source_version")
    op.drop_column("targets", "chembl_id")
