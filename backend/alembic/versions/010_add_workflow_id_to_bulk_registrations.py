"""Add workflow_id to bulk_registrations for Temporal workflow tracking.

Revision ID: 010
Revises: 009
"""

import sqlalchemy as sa
from alembic import op

revision = "010"
down_revision = "009"


def upgrade() -> None:
    op.add_column(
        "bulk_registrations",
        sa.Column("workflow_id", sa.String(255), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("bulk_registrations", "workflow_id")
