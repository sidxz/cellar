"""Add lock state columns to protocols.

Mirrors the existing Run lock pattern (is_locked / locked_at / locked_by /
lock_reason). Lock is orthogonal to DRAFT/ACTIVE/RETIRED — a workflow gate
the user opts into during regulatory submissions or cross-team
coordination. While locked, every Protocol mutation method (lock/unlock
themselves are the exceptions) raises ConflictError until unlock.

All columns are nullable additions; existing rows default to is_locked=false
so no backfill is required.

Revision ID: 023
Revises: 022
"""

import sqlalchemy as sa
from alembic import op

revision = "023"
down_revision = "022"


def upgrade() -> None:
    op.add_column(
        "protocols",
        sa.Column(
            "is_locked",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "protocols",
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "protocols",
        sa.Column("locked_by", sa.Uuid(), nullable=True),
    )
    op.add_column(
        "protocols",
        sa.Column("lock_reason", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("protocols", "lock_reason")
    op.drop_column("protocols", "locked_by")
    op.drop_column("protocols", "locked_at")
    op.drop_column("protocols", "is_locked")
