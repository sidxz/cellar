"""108 — a CDD import keeps its run report.

Adds ``cdd_molecule_imports.report`` (JSONB, NULL): what the run added and skipped.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "108_cdd_import_report"
down_revision = "107_cdd_registration_mapping"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("cdd_molecule_imports", sa.Column("report", postgresql.JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column("cdd_molecule_imports", "report")
