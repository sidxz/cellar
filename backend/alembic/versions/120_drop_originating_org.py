"""Molecules and CDD imports no longer reference Cellar's local org list.

A molecule's orgs are Duar orgs now (``registered_by_org_id``,
``disclosed_by_org_id``; migration 117). Dropping each column drops its FK to
``organizations``. The local list stays for vendors (batch suppliers).
Downgrade re-adds the columns as nullable with no FK: the old local ids are gone.
"""

import sqlalchemy as sa
from alembic import op

revision = "120_drop_originating_org"
down_revision = "119_disclosure_requester_orgs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column("molecules", "originating_org_id")
    op.drop_column("cdd_molecule_imports", "originating_org_id")


def downgrade() -> None:
    op.add_column(
        "cdd_molecule_imports", sa.Column("originating_org_id", sa.Uuid(), nullable=True)
    )
    op.add_column("molecules", sa.Column("originating_org_id", sa.Uuid(), nullable=True))
