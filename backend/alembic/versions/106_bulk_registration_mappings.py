"""106 — saved column mappings for the bulk-registration wizard.

Table ``bulk_registration_mappings``: a named, workspace-scoped "Match columns"
choice (``columns`` = list of {header, target, source}), unique by name per
workspace.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "106_bulk_registration_mappings"
down_revision = "105_cdd_batch_name_backfill"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "bulk_registration_mappings",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("workspace_id", sa.Uuid(), nullable=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("columns", postgresql.JSONB(), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True
        ),
        sa.UniqueConstraint("workspace_id", "name", name="uq_bulk_registration_mapping_ws_name"),
    )
    op.create_index(
        "ix_bulk_registration_mappings_workspace_id",
        "bulk_registration_mappings",
        ["workspace_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_bulk_registration_mappings_workspace_id", table_name="bulk_registration_mappings"
    )
    op.drop_table("bulk_registration_mappings")
