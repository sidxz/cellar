"""Add Protocol.pos_control_signal — wet-lab convention flag for POS controls.

Resolves the ambiguity between two HTS labelings:
- "high" (default): POS wells produce HIGH raw signal (uninhibited / DMSO).
- "low":            POS wells produce LOW raw signal (known inhibitor / blank).

Existing rows default to "high" — same convention the formulas already
assumed, so historical computations remain stable until the user opts in.

Revision ID: 019
Revises: 018
"""

import sqlalchemy as sa
from alembic import op

revision = "019"
down_revision = "018"


def upgrade() -> None:
    op.add_column(
        "protocols",
        sa.Column(
            "pos_control_signal",
            sa.String(10),
            nullable=False,
            server_default="high",
        ),
    )


def downgrade() -> None:
    op.drop_column("protocols", "pos_control_signal")
