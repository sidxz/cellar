"""046 — used_in_collections JSONB on collection_import_templates.

Append-only list of collection_ids this template has been applied to.
Enables "used here before" filter + tier-1 auto-pick priority in the
mapping step UX.

Revision ID: 046_template_used_in_collections
Revises: 045_collection_import_templates
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "046_template_used_in_collections"
down_revision = "045_collection_import_templates"


def upgrade() -> None:
    op.add_column(
        "collection_import_templates",
        sa.Column(
            "used_in_collections",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )


def downgrade() -> None:
    op.drop_column("collection_import_templates", "used_in_collections")
