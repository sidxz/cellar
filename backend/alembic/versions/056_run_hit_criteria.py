"""per-run hit criteria

Hit criteria become an attributable per-run analytical decision, distinct from
the protocol's ``recommended_hit_criteria`` (which stays the SOP suggestion). A
run starts unset and the protocol value is only ever *recommended*, never
auto-applied.

Three columns on ``runs``, all nullable:
  - ``hit_criteria`` (JSONB): NULL = unset (show the protocol recommendation);
    a JSON list (possibly empty ``[]`` = "no threshold, show all — recorded") =
    a recorded decision. Same per-rule shape as
    ``protocols.recommended_hit_criteria``.
  - ``hit_criteria_set_by`` (uuid), ``hit_criteria_set_at`` (timestamptz):
    provenance, non-NULL iff ``hit_criteria`` is non-NULL.

Revision ID: 056_run_hit_criteria
Revises: 055_run_collections_m2m
Create Date: 2026-06-09
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "056_run_hit_criteria"
down_revision = "055_run_collections_m2m"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("runs", sa.Column("hit_criteria", JSONB(), nullable=True))
    op.add_column("runs", sa.Column("hit_criteria_set_by", sa.Uuid(), nullable=True))
    op.add_column(
        "runs",
        sa.Column("hit_criteria_set_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("runs", "hit_criteria_set_at")
    op.drop_column("runs", "hit_criteria_set_by")
    op.drop_column("runs", "hit_criteria")
