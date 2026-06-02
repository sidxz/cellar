"""047 — tagging: tags registry + per-entity link tables + backfill.

Creates the tag registry, four per-entity link tables (molecule/protocol/
project/collection), a tag_links_all UNION ALL view, and backfills the legacy
molecules.tags strings as value-less tags. The molecules.tags column is dropped
later in migration 048, after all readers are repointed.

Revision ID: 047_tagging
Revises: 046_template_used_in_collections
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

from cellar.infrastructure.persistence.sqlalchemy.tagging.backfill_sql import (
    BACKFILL_LINKS_SQL,
    BACKFILL_TAGS_SQL,
)

revision = "047_tagging"
down_revision = "046_template_used_in_collections"


def _create_link_table(name: str, entity_col: str, entity_table: str) -> None:
    op.create_table(
        name,
        sa.Column(
            entity_col,
            sa.Uuid(),
            sa.ForeignKey(f"{entity_table}.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "tag_id",
            sa.Uuid(),
            sa.ForeignKey("tags.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("assigned_by", sa.Uuid(), nullable=False),
        sa.Column(
            "assigned_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(f"ix_{name}_tag_id", name, ["tag_id"])


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    # --- tag registry ---
    op.create_table(
        "tags",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("key", sa.String(length=128), nullable=False),
        sa.Column("value", sa.String(length=256), nullable=True),
        sa.Column("normalized_key", sa.String(length=128), nullable=False),
        sa.Column("normalized_value", sa.String(length=256), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
    )
    op.create_index("ix_tags_workspace_id", "tags", ["workspace_id"])
    op.create_index("ix_tags_ws_created_by", "tags", ["workspace_id", "created_by"])
    # Unique dedup index — NULLS NOT DISTINCT so value-less tags collapse.
    op.execute(
        "CREATE UNIQUE INDEX uq_tags_ws_norm ON tags "
        "(workspace_id, normalized_key, normalized_value) NULLS NOT DISTINCT"
    )
    # Trigram GIN indexes for autocomplete.
    op.execute(
        "CREATE INDEX ix_tags_norm_key_trgm ON tags "
        "USING gin (normalized_key gin_trgm_ops)"
    )
    op.execute(
        "CREATE INDEX ix_tags_norm_value_trgm ON tags "
        "USING gin (normalized_value gin_trgm_ops)"
    )

    # --- per-entity link tables ---
    _create_link_table("molecule_tags", "molecule_id", "molecules")
    _create_link_table("protocol_tags", "protocol_id", "protocols")
    _create_link_table("project_tags", "project_id", "projects")
    _create_link_table("collection_tags", "collection_id", "collections")

    # --- cross-type view ---
    op.execute(
        """
        CREATE VIEW tag_links_all AS
            SELECT 'Molecule' AS entity_type, molecule_id AS entity_id,
                   tag_id, assigned_by, assigned_at FROM molecule_tags
            UNION ALL
            SELECT 'Protocol', protocol_id, tag_id, assigned_by, assigned_at
                   FROM protocol_tags
            UNION ALL
            SELECT 'Project', project_id, tag_id, assigned_by, assigned_at
                   FROM project_tags
            UNION ALL
            SELECT 'Collection', collection_id, tag_id, assigned_by, assigned_at
                   FROM collection_tags
        """
    )

    # --- backfill legacy molecules.tags ---
    op.execute(BACKFILL_TAGS_SQL)
    op.execute(BACKFILL_LINKS_SQL)


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS tag_links_all")
    op.drop_table("collection_tags")
    op.drop_table("project_tags")
    op.drop_table("protocol_tags")
    op.drop_table("molecule_tags")
    op.drop_table("tags")
