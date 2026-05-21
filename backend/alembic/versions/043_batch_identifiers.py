"""043 — batch_identifiers table.

Lets a Batch carry N external/foreign identifiers (CDD batch_id, vendor lot,
partner batch number, etc.). Imports referencing a batch by its name in
some other system now resolve through this table.

Mirrors the shape of molecule_identifiers exactly. Unique (workspace_id,
identifier) — an external ref cannot point to two batches in the same
workspace.

Revision ID: 043_batch_identifiers
Revises: 042_configurable_reg_prefix
Create Date: 2026-05-21
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "043_batch_identifiers"
down_revision: str | None = "042_configurable_reg_prefix"
branch_labels: None = None
depends_on: None = None


def upgrade() -> None:
    op.create_table(
        "batch_identifiers",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, primary_key=True),
        sa.Column(
            "batch_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("batches.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("identifier", sa.String(length=255), nullable=False),
        sa.Column("identifier_type", sa.String(length=50), nullable=False),
        sa.Column("source", sa.String(length=255), nullable=False),
        sa.Column("registered_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("workspace_id", "identifier", name="uq_batch_ws_identifier"),
    )
    op.create_index(
        "ix_batch_identifiers_workspace_id",
        "batch_identifiers",
        ["workspace_id"],
    )
    op.create_index(
        "ix_batch_identifiers_batch_id",
        "batch_identifiers",
        ["batch_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_batch_identifiers_batch_id", table_name="batch_identifiers")
    op.drop_index("ix_batch_identifiers_workspace_id", table_name="batch_identifiers")
    op.drop_table("batch_identifiers")
