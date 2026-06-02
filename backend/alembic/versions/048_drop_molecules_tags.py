"""048 — drop the legacy molecules.tags column.

Superseded by the tagging system (tags registry + per-entity link tables,
migration 047). All backend readers/writers were removed in Phase 3.

Revision ID: 048_drop_molecules_tags
Revises: 047_tagging
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "048_drop_molecules_tags"
down_revision = "047_tagging"


def upgrade() -> None:
    op.drop_column("molecules", "tags")


def downgrade() -> None:
    op.add_column(
        "molecules",
        sa.Column("tags", postgresql.JSON(), nullable=True),
    )
