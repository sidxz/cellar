"""110 — a CDD import keeps what a resume needs.

Adds ``cdd_molecule_imports.cdd_export_id`` (INTEGER, NULL): the CDD export the run
reads from disk, and ``run_settings`` (JSONB, NULL): the options the run started with.
Both NULL for runs recorded before this, which cannot be resumed.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "110_cdd_import_resume"
down_revision = "109_molecule_ident_lower_idx"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("cdd_molecule_imports", sa.Column("cdd_export_id", sa.Integer(), nullable=True))
    op.add_column(
        "cdd_molecule_imports", sa.Column("run_settings", postgresql.JSONB(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("cdd_molecule_imports", "run_settings")
    op.drop_column("cdd_molecule_imports", "cdd_export_id")
