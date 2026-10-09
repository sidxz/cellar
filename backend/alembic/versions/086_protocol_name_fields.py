"""protocol name fields: discriminator, name base (collision key), name flag; longer names

Revision ID: 086_protocol_name_fields
Revises: 085_naming_labels
Create Date: 2026-10-08
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "086_protocol_name_fields"
down_revision: str | None = "085_naming_labels"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "protocols",
        "name",
        type_=sa.String(400),
        existing_type=sa.String(200),
        existing_nullable=False,
    )
    op.add_column("protocols", sa.Column("discriminator", sa.String(40), nullable=True))
    op.add_column("protocols", sa.Column("name_base", sa.String(400), nullable=True))
    op.add_column("protocols", sa.Column("name_flag", sa.String(30), nullable=True))
    op.execute("UPDATE protocols SET name_base = name")
    op.alter_column("protocols", "name_base", nullable=False)
    op.create_index(
        "ix_protocol_ws_name_base", "protocols", ["workspace_id", sa.text("lower(name_base)")]
    )


def downgrade() -> None:
    op.drop_index("ix_protocol_ws_name_base", table_name="protocols")
    op.drop_column("protocols", "name_flag")
    op.drop_column("protocols", "name_base")
    op.drop_column("protocols", "discriminator")
    op.alter_column(
        "protocols",
        "name",
        type_=sa.String(200),
        existing_type=sa.String(400),
        existing_nullable=False,
    )
