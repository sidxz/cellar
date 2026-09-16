"""067 — plate_groups metadata columns (spec 2026-08-25 §5)

Legacy-set metadata on the group: state, storage location, initial
volume/concentration, compound count, scientist. All nullable; measurements
are Float per the inventory convention (not Numeric).

Revision ID: 067_plate_group_metadata
Revises: 066_drop_plates_private
"""

import sqlalchemy as sa
from alembic import op

revision = "067_plate_group_metadata"
down_revision = "066_drop_plates_private"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("plate_groups", sa.Column("state", sa.String(50), nullable=True))
    op.add_column("plate_groups", sa.Column("storage_location_id", sa.Uuid(), nullable=True))
    op.add_column("plate_groups", sa.Column("initial_volume_ul", sa.Float(), nullable=True))
    op.add_column(
        "plate_groups", sa.Column("initial_concentration_mm", sa.Float(), nullable=True)
    )
    op.add_column("plate_groups", sa.Column("compound_count", sa.Integer(), nullable=True))
    op.add_column("plate_groups", sa.Column("scientist", sa.String(200), nullable=True))
    op.create_foreign_key(
        "fk_plate_groups_storage_location",
        "plate_groups",
        "storage_locations",
        ["storage_location_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_plate_groups_storage_location", "plate_groups", type_="foreignkey")
    for col in (
        "scientist",
        "compound_count",
        "initial_concentration_mm",
        "initial_volume_ul",
        "storage_location_id",
        "state",
    ):
        op.drop_column("plate_groups", col)
