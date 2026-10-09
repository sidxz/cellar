"""protocol forms serve a category; at most one default per category

Revision ID: 089_protocol_form_category
Revises: 088_canonical_units
Create Date: 2026-10-08
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "089_protocol_form_category"
down_revision: str | None = "088_canonical_units"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

_NIL = "'00000000-0000-0000-0000-000000000000'::uuid"


def upgrade() -> None:
    op.add_column("protocol_forms", sa.Column("category_id", sa.Uuid(), nullable=True))
    op.add_column(
        "protocol_forms",
        sa.Column(
            "assay_format_from_target", sa.Boolean(), nullable=False, server_default="false"
        ),
    )
    op.create_foreign_key(
        "fk_protocol_form_category",
        "protocol_forms",
        "protocol_categories",
        ["category_id"],
        ["id"],
        ondelete="SET NULL",
    )
    # "At most one default" was never enforced: keep the most recently updated per workspace.
    op.execute(
        """
        update protocol_forms f set is_default = false
        where f.is_default and exists (
            select 1 from protocol_forms g
            where g.workspace_id = f.workspace_id and g.is_default
              and (g.updated_at, g.id) > (f.updated_at, f.id)
        )
        """
    )
    op.execute(
        f"create unique index ux_protocol_form_default on protocol_forms "
        f"(workspace_id, coalesce(category_id, {_NIL})) where is_default"
    )


def downgrade() -> None:
    op.execute("drop index if exists ux_protocol_form_default")
    op.drop_constraint("fk_protocol_form_category", "protocol_forms", type_="foreignkey")
    op.drop_column("protocol_forms", "assay_format_from_target")
    op.drop_column("protocol_forms", "category_id")
