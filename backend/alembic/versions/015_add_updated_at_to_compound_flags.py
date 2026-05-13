"""Add updated_at column to compound_flags.

The CompoundFlagModel inherits EntityModelMixin which declares both
created_at and updated_at, but migration 007 only created created_at.

Revision ID: 015
Revises: 014
"""

import sqlalchemy as sa
from alembic import op

revision = "015"
down_revision = "014"


def upgrade() -> None:
    op.add_column(
        "compound_flags",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )


def downgrade() -> None:
    op.drop_column("compound_flags", "updated_at")
