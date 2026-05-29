"""045 — collection_import_templates table.

Workspace-scoped saved column mappings for the collection bulk-import
wizard. Shape mirrors run_import_templates (migration 016) but the
mapping payload's identifier roles are different.

Revision ID: 045_collection_import_templates
Revises: 044_batch_id_mirror_fk
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "045_collection_import_templates"
down_revision = "044_batch_id_mirror_fk"


def upgrade() -> None:
    op.create_table(
        "collection_import_templates",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("column_mapping", postgresql.JSONB(), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "workspace_id", "name", name="uq_collection_import_template_ws_name"
        ),
    )
    op.create_index(
        "ix_collection_import_template_ws",
        "collection_import_templates",
        ["workspace_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_collection_import_template_ws",
        table_name="collection_import_templates",
    )
    op.drop_table("collection_import_templates")
