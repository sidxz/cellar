"""naming labels: admin overrides of how ontology terms read inside protocol names

Revision ID: 085_naming_labels
Revises: 084_protocol_categories
Create Date: 2026-10-08
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "085_naming_labels"
down_revision: str | None = "084_protocol_categories"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "naming_labels",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("term_id", sa.String(300), nullable=False),
        sa.Column("term_label", sa.String(300), nullable=False),
        sa.Column("ontology_source", sa.String(40), nullable=False),
        sa.Column("short_label", sa.String(60), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("workspace_id", "term_id", name="uq_naming_label_ws_term"),
    )
    op.create_index("ix_naming_labels_workspace_id", "naming_labels", ["workspace_id"])


def downgrade() -> None:
    op.drop_index("ix_naming_labels_workspace_id", table_name="naming_labels")
    op.drop_table("naming_labels")
