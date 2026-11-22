"""A molecule records who registered it, their Duar org, and the discloser's Duar org.

Plain uuid columns with no FK (orgs live in Duar). Schema only:
``scripts/backfill_duar_orgs.py`` fills existing rows.
"""

import sqlalchemy as sa
from alembic import op

revision = "117_molecule_registrant_org"
down_revision = "116_owner_and_creator_orgs"
branch_labels = None
depends_on = None

_COLUMNS = ("registered_by", "registered_by_org_id", "disclosed_by_org_id")


def upgrade() -> None:
    for name in _COLUMNS:
        op.add_column("molecules", sa.Column(name, sa.Uuid(), nullable=True))


def downgrade() -> None:
    for name in reversed(_COLUMNS):
        op.drop_column("molecules", name)
