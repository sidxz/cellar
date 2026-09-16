"""070 — plate_groups.collection_id (spec 2026-08-26 §4)

Optional link from a plate group (any level) to the Collection it physically
realizes. FK SET NULL on collection delete, indexed. No backfill.

Revision ID: 070_plate_group_collection
Revises: 069_run_plate_registered_plate
"""

import sqlalchemy as sa
from alembic import op

revision = "070_plate_group_collection"
down_revision = "069_run_plate_registered_plate"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("plate_groups", sa.Column("collection_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_plate_groups_collection",
        "plate_groups",
        "collections",
        ["collection_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_plate_groups_collection", "plate_groups", ["collection_id"])


def downgrade() -> None:
    op.drop_index("ix_plate_groups_collection", table_name="plate_groups")
    op.drop_constraint("fk_plate_groups_collection", "plate_groups", type_="foreignkey")
    op.drop_column("plate_groups", "collection_id")
