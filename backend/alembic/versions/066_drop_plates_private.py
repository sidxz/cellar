"""066 — drop org_plate_policies.plates_private (spec 2026-08-25 §3)

Plate visibility is strict for every org (own plates + plates on loan to
me; workspace admins see all), so the per-org opt-in privacy flag is gone.

Revision ID: 066_drop_plates_private
Revises: 065_target_mirror_columns
"""

import sqlalchemy as sa
from alembic import op

revision = "066_drop_plates_private"
down_revision = "065_target_mirror_columns"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column("org_plate_policies", "plates_private")


def downgrade() -> None:
    op.add_column(
        "org_plate_policies",
        sa.Column("plates_private", sa.Boolean(), nullable=False, server_default="false"),
    )
