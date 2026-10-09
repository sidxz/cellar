"""protocol aliases: former names and nicknames (searchable, never the name)

Revision ID: 083_protocol_aliases
Revises: 082_protocol_code
Create Date: 2026-10-08
"""

from __future__ import annotations

from typing import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "083_protocol_aliases"
down_revision: str | None = "082_protocol_code"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "protocol_aliases",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("protocol_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("label", sa.String(400), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["protocol_id"], ["protocols.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_protocol_aliases_protocol", "protocol_aliases", ["protocol_id"])


def downgrade() -> None:
    op.drop_index("ix_protocol_aliases_protocol", table_name="protocol_aliases")
    op.drop_table("protocol_aliases")
