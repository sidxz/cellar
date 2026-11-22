"""Disclosure requests and bulk disclosures record the requester's Duar org.

Plain uuid columns with no FK (orgs live in Duar). ``disclosing_org_id`` and
``partner_org_id`` keep their columns and now hold Duar ids; the backfill
script repoints existing rows. Schema only.
"""

import sqlalchemy as sa
from alembic import op

revision = "119_disclosure_requester_orgs"
down_revision = "118_cdd_import_discloser"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "disclosure_requests", sa.Column("requested_by_org_id", sa.Uuid(), nullable=True)
    )
    op.add_column("bulk_disclosures", sa.Column("submitted_by_org_id", sa.Uuid(), nullable=True))


def downgrade() -> None:
    op.drop_column("bulk_disclosures", "submitted_by_org_id")
    op.drop_column("disclosure_requests", "requested_by_org_id")
