"""A campaign can be managed by another app in the realm (e.g. DAIKON's rounds)."""

import sqlalchemy as sa
from alembic import op

revision = "112_campaign_managed_by"
down_revision = "111_cdd_import_failure_reason"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("campaign", sa.Column("managed_by", sa.String(100), nullable=True))
    op.add_column("campaign", sa.Column("managed_url", sa.Text(), nullable=True))
    op.add_column("campaign", sa.Column("managed_label", sa.String(100), nullable=True))


def downgrade() -> None:
    op.drop_column("campaign", "managed_label")
    op.drop_column("campaign", "managed_url")
    op.drop_column("campaign", "managed_by")
