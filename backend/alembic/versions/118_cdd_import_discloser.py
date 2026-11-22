"""A CDD molecule import keeps the discloser pick it started with, so a resume uses it.

``disclosed_by_org_id`` is a Duar org id (no FK). Schema only.
"""

import sqlalchemy as sa
from alembic import op

revision = "118_cdd_import_discloser"
down_revision = "117_molecule_registrant_org"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("cdd_molecule_imports", sa.Column("disclosed_by", sa.Uuid(), nullable=True))
    op.add_column(
        "cdd_molecule_imports", sa.Column("disclosed_by_org_id", sa.Uuid(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("cdd_molecule_imports", "disclosed_by_org_id")
    op.drop_column("cdd_molecule_imports", "disclosed_by")
