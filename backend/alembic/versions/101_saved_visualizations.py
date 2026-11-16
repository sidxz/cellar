"""101 — saved_visualizations table.

A named workbench view: the source it shows (``source``, plus every protocol it
names in ``protocol_ids`` for the per-protocol listing), the level, and the plot
and filter settings (``config``). Private to its creator or shared with a project.

Revision ID: 101_saved_visualizations
Revises: 100_export_requested_by_email
Create Date: 2026-11-16
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ARRAY, JSONB

revision = "101_saved_visualizations"
down_revision = "100_export_requested_by_email"


def upgrade() -> None:
    op.create_table(
        "saved_visualizations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("source", JSONB(), nullable=False),
        sa.Column("protocol_ids", ARRAY(sa.Uuid()), nullable=False),
        sa.Column("level", sa.String(20), nullable=False),
        sa.Column("config", JSONB(), nullable=False),
        sa.Column("visibility", sa.String(20), nullable=False),
        sa.Column(
            "project_id",
            sa.Uuid(),
            sa.ForeignKey("projects.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_saved_visualizations_workspace_id", "saved_visualizations", ["workspace_id"]
    )
    op.create_index(
        "ix_saved_visualizations_ws_creator",
        "saved_visualizations",
        ["workspace_id", "created_by"],
    )
    op.create_index(
        "ix_saved_visualizations_protocol_ids",
        "saved_visualizations",
        ["protocol_ids"],
        postgresql_using="gin",
    )


def downgrade() -> None:
    op.drop_index("ix_saved_visualizations_protocol_ids", table_name="saved_visualizations")
    op.drop_index("ix_saved_visualizations_ws_creator", table_name="saved_visualizations")
    op.drop_index("ix_saved_visualizations_workspace_id", table_name="saved_visualizations")
    op.drop_table("saved_visualizations")
