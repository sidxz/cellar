"""062 — plate_groups table + registered_plates.group_id

Revision ID: 062_plate_groups
Revises: 061_org_plate_policies
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "062_plate_groups"
down_revision = "061_org_plate_policies"
branch_labels = None
depends_on = None

# NULLS NOT DISTINCT (PG15+) is unavailable through sa.UniqueConstraint /
# op.create_index — raw SQL, exactly like migration 049. Needed because
# parent_group_id IS NULL for root groups and two roots must not share a name.
_CREATE_UNIQUE_SQL = """
CREATE UNIQUE INDEX uq_plate_groups_ws_org_parent_name ON plate_groups
    (workspace_id, owner_org_id, parent_group_id, name)
    NULLS NOT DISTINCT;
"""


def upgrade() -> None:
    op.create_table(
        "plate_groups",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("owner_org_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(300), nullable=False),
        sa.Column("parent_group_id", sa.Uuid(), nullable=True),
        sa.Column("group_type", sa.String(100), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["parent_group_id"],
            ["plate_groups.id"],
            name="fk_plate_groups_parent",
            ondelete="RESTRICT",
        ),
    )
    op.create_index("ix_plate_groups_ws_org", "plate_groups", ["workspace_id", "owner_org_id"])
    op.create_index("ix_plate_groups_parent", "plate_groups", ["parent_group_id"])
    op.execute(_CREATE_UNIQUE_SQL)

    op.add_column("registered_plates", sa.Column("group_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_registered_plates_group",
        "registered_plates",
        "plate_groups",
        ["group_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_reg_plate_group", "registered_plates", ["group_id"])


def downgrade() -> None:
    op.drop_index("ix_reg_plate_group", table_name="registered_plates")
    op.drop_constraint("fk_registered_plates_group", "registered_plates", type_="foreignkey")
    op.drop_column("registered_plates", "group_id")
    op.execute("DROP INDEX IF EXISTS uq_plate_groups_ws_org_parent_name")
    op.drop_index("ix_plate_groups_parent", table_name="plate_groups")
    op.drop_index("ix_plate_groups_ws_org", table_name="plate_groups")
    op.drop_table("plate_groups")
