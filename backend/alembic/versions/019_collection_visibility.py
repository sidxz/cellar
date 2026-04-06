"""Add visibility to collections.

Revision ID: 019
Revises: 018
"""

from alembic import op
import sqlalchemy as sa

revision = "019"
down_revision = "018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "collections",
        sa.Column("visibility", sa.String(20), nullable=False, server_default="private"),
    )


def downgrade() -> None:
    op.drop_column("collections", "visibility")
