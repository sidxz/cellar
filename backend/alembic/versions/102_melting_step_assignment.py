"""102 — a melting step can be assigned to a temperature window.

Four nullable columns on ``melting_steps``: the window's name, the reason, who
assigned it and when. They are apart from ``reason`` / ``changed_by`` /
``changed_at``, which describe the review (accept, reject, correct).

Revision ID: 102_melting_step_assignment
Revises: 101_saved_visualizations
Create Date: 2026-11-17
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "102_melting_step_assignment"
down_revision = "101_saved_visualizations"


def upgrade() -> None:
    op.add_column("melting_steps", sa.Column("assigned_window", sa.String(60), nullable=True))
    op.add_column("melting_steps", sa.Column("assignment_reason", sa.String(500), nullable=True))
    op.add_column("melting_steps", sa.Column("assigned_by", sa.Uuid(), nullable=True))
    op.add_column(
        "melting_steps", sa.Column("assigned_at", sa.DateTime(timezone=True), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("melting_steps", "assigned_at")
    op.drop_column("melting_steps", "assigned_by")
    op.drop_column("melting_steps", "assignment_reason")
    op.drop_column("melting_steps", "assigned_window")
