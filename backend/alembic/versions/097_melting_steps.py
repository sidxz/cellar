"""melting steps: melting_steps table, melt_config on readout definitions

Every melting step an instrument reported on a trace becomes a reviewable row.
Existing traces are seeded: one unreviewed instrument step per reported transition.

Revision ID: 097_melting_steps
Revises: 096_null_non_finite_well_doses
Create Date: 2026-11-13
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "097_melting_steps"
down_revision: str | None = "096_null_non_finite_well_doses"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "melting_steps",
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
        sa.Column("source", sa.String(20), nullable=False),
        sa.Column("value", postgresql.DOUBLE_PRECISION(), nullable=False),
        sa.Column("instrument_value", postgresql.DOUBLE_PRECISION(), nullable=True),
        sa.Column("instrument_label", sa.String(200), nullable=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("reason", sa.String(500), nullable=True),
        sa.Column("changed_by", sa.Uuid(), nullable=True),
        sa.Column("changed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("source IN ('instrument', 'manual')", name="ck_melting_step_source"),
        sa.CheckConstraint(
            "status IN ('unreviewed', 'accepted', 'rejected')", name="ck_melting_step_status"
        ),
    )
    op.create_index("ix_melting_steps_workspace_id", "melting_steps", ["workspace_id"])
    op.create_index("ix_melting_step_run", "melting_steps", ["run_id"])
    op.add_column(
        "readout_definitions", sa.Column("melt_config", postgresql.JSONB(), nullable=True)
    )
    op.execute(
        """
        INSERT INTO melting_steps (id, workspace_id, run_id, well_id, channel_key, source, value,
               instrument_value, instrument_label, status, version, created_at, updated_at)
        SELECT gen_random_uuid(), mc.workspace_id, mc.run_id, mc.well_id, mc.channel_key,
               'instrument', (r->>'value')::float8, (r->>'value')::float8, r->>'label',
               'unreviewed', 1, now(), now()
        FROM measured_curves mc, jsonb_array_elements(mc.reported) r
        WHERE r->>'kind' = 'transition'
        """
    )


def downgrade() -> None:
    op.drop_column("readout_definitions", "melt_config")
    op.drop_index("ix_melting_step_run", table_name="melting_steps")
    op.drop_index("ix_melting_steps_workspace_id", table_name="melting_steps")
    op.drop_table("melting_steps")
