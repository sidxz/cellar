"""Keep CDD import failure reasons available to reports after a reload."""

import sqlalchemy as sa
from alembic import op

revision = "111_cdd_import_failure_reason"
down_revision = "110_cdd_import_resume"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for table in ("cdd_molecule_imports", "cdd_plate_imports"):
        op.add_column(table, sa.Column("failure_reason", sa.Text(), nullable=True))


def downgrade() -> None:
    for table in ("cdd_plate_imports", "cdd_molecule_imports"):
        op.drop_column(table, "failure_reason")
