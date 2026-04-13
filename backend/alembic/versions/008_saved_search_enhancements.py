"""Add description, last_run_at, result_count to saved_searches.

Supports search execution metadata and optional description field
for the SavedSearch revamp.

Revision ID: 008
Revises: 007
"""

import sqlalchemy as sa
from alembic import op

revision = "008"
down_revision = "007"


def upgrade() -> None:
    op.add_column(
        "saved_searches",
        sa.Column("description", sa.Text(), nullable=True),
    )
    op.add_column(
        "saved_searches",
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "saved_searches",
        sa.Column("result_count", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("saved_searches", "result_count")
    op.drop_column("saved_searches", "last_run_at")
    op.drop_column("saved_searches", "description")
