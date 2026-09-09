"""072 — registration provenance: scientist_name on molecules

The person half of provenance. originating_org_id already records the org;
DisclosureRequest already records scientist_name. Registration recorded
neither, so a molecule registered through the API had an org but no person.

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


def downgrade() -> None:
    op.drop_column("molecules", "scientist_name")
