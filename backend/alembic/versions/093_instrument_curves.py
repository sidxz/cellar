"""instrument curves: measured_curves table, holder columns on plates, label on wells

Revision ID: 093_instrument_curves
Revises: 092_protocol_references
Create Date: 2026-11-12

Existing plates read as plate holders through the server default; holder size and
well label stay empty on existing rows.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "093_instrument_curves"
down_revision: str | None = "092_protocol_references"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "plates",
        sa.Column("holder_kind", sa.String(20), nullable=False, server_default="plate"),
    )
    op.add_column("plates", sa.Column("holder_rows", sa.Integer(), nullable=True))
    op.add_column("plates", sa.Column("holder_columns", sa.Integer(), nullable=True))
    op.add_column("wells", sa.Column("label", sa.String(200), nullable=True))

    op.create_table(
        "measured_curves",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column(
            "run_id",
            sa.Uuid(),
            sa.ForeignKey("runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("well_id", sa.Uuid(), nullable=False),
        sa.Column("channel_key", sa.String(100), nullable=False),
        sa.Column("channel_label", sa.String(200), nullable=False),
        sa.Column("x_unit", sa.String(40), nullable=False),
        sa.Column("y_unit", sa.String(40), nullable=True),
        sa.Column("channel_order", sa.Integer(), nullable=False),
        sa.Column("x", postgresql.ARRAY(postgresql.DOUBLE_PRECISION()), nullable=False),
        sa.Column("y", postgresql.ARRAY(postgresql.DOUBLE_PRECISION()), nullable=False),
        sa.Column(
            "reported",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("reader", sa.String(100), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("well_id", "channel_key", name="uq_measured_curve_well_channel"),
        sa.CheckConstraint(
            "cardinality(x) = cardinality(y) AND cardinality(x) >= 2",
            name="ck_measured_curve_points",
        ),
    )
    op.create_index("ix_measured_curves_workspace_id", "measured_curves", ["workspace_id"])
    op.create_index("ix_measured_curve_run_channel", "measured_curves", ["run_id", "channel_key"])


def downgrade() -> None:
    op.drop_index("ix_measured_curve_run_channel", table_name="measured_curves")
    op.drop_index("ix_measured_curves_workspace_id", table_name="measured_curves")
    op.drop_table("measured_curves")
    op.drop_column("wells", "label")
    op.drop_column("plates", "holder_columns")
    op.drop_column("plates", "holder_rows")
    op.drop_column("plates", "holder_kind")
