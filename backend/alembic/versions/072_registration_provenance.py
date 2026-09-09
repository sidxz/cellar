"""072 — registration + disclosure provenance

- molecules.scientist_name: the person half of provenance. originating_org_id
  already records the org; DisclosureRequest already records scientist_name.
  Registration recorded neither.
- molecules.disclosure_date / disclosure_requests.disclosure_date: a declared
  (possibly historic) disclosure date, like invention_date. The observed
  stamps (disclosed_at, requested_at) are kept alongside it — a declared
  date and a recorded-at time are different facts.

Revision ID: 072_registration_provenance
Revises: 071_shipment_container
"""

import sqlalchemy as sa
from alembic import op

revision = "072_registration_provenance"
down_revision = "071_shipment_container"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("molecules", sa.Column("scientist_name", sa.String(200), nullable=True))
    op.add_column("molecules", sa.Column("disclosure_date", sa.Date(), nullable=True))
    op.add_column("disclosure_requests", sa.Column("disclosure_date", sa.Date(), nullable=True))


def downgrade() -> None:
    op.drop_column("disclosure_requests", "disclosure_date")
    op.drop_column("molecules", "disclosure_date")
    op.drop_column("molecules", "scientist_name")
