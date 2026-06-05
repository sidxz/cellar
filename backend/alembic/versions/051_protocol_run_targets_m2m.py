"""protocol/run multi-target M2M

Replaces the scalar ``protocols.target_id`` with two pure association tables:
``protocol_targets`` (a protocol's direct targets) and ``run_targets`` (each
run's independent target set). A protocol's *effective* target list is computed
at read time as ``protocol_targets`` union the distinct targets of all its runs, so
adding a target to a run rolls up to the protocol and removing the last run
reference auto-prunes inherited (non-direct) targets.

The existing single ``target_id`` is backfilled as a *direct* protocol target,
then the column is dropped.

Revision ID: 051_protocol_run_targets_m2m
Revises: 050_tagging_expansion
Create Date: 2026-06-05
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "051_protocol_run_targets_m2m"
down_revision = "050_tagging_expansion"
branch_labels = None
depends_on = None


def _link_table(name: str, owner_col: str, owner_table: str) -> None:
    op.create_table(
        name,
        sa.Column(
            owner_col,
            sa.Uuid(),
            sa.ForeignKey(f"{owner_table}.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "target_id",
            sa.Uuid(),
            sa.ForeignKey("targets.id", ondelete="CASCADE"),
            primary_key=True,
        ),
    )
    op.create_index(f"ix_{name}_target", name, ["target_id"])


def upgrade() -> None:
    _link_table("protocol_targets", "protocol_id", "protocols")
    _link_table("run_targets", "run_id", "runs")
    # Backfill: the existing single target becomes a DIRECT protocol target.
    op.execute(
        "INSERT INTO protocol_targets (protocol_id, target_id) "
        "SELECT id, target_id FROM protocols WHERE target_id IS NOT NULL"
    )
    op.drop_column("protocols", "target_id")


def downgrade() -> None:
    op.add_column(
        "protocols",
        sa.Column(
            "target_id",
            sa.Uuid(),
            sa.ForeignKey("targets.id"),
            nullable=True,
        ),
    )
    # Lossy restore: only protocols with exactly one direct target round-trip.
    op.execute(
        "UPDATE protocols p SET target_id = sub.target_id FROM ("
        "  SELECT protocol_id, MIN(target_id::text)::uuid AS target_id "
        "  FROM protocol_targets GROUP BY protocol_id HAVING COUNT(*) = 1"
        ") sub WHERE p.id = sub.protocol_id"
    )
    op.drop_table("run_targets")
    op.drop_table("protocol_targets")
