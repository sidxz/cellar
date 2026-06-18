"""059 — protocol fingerprint column + trigram name index

Adds the structural Assay Fingerprint (JSONB) and a pg_trgm GIN index on
protocols.name to back similarity blocking. pg_trgm was installed in 047.

Revision ID: 059_protocol_fingerprint
Revises: 058_sar_activity_projections
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "059_protocol_fingerprint"
down_revision = "058_sar_activity_projections"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.add_column("protocols", sa.Column("fingerprint", JSONB(), nullable=True))
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_protocols_name_trgm "
        "ON protocols USING gin (name gin_trgm_ops)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_protocols_name_trgm")
    op.drop_column("protocols", "fingerprint")
