"""050 — tagging expansion: link tables for run/campaign/batch/registered_plate.

Adds four per-entity tag link tables and recreates the tag_links_all UNION view
to cover all eight taggable entity types. No backfill (these entities carry no
legacy tag data).

Revision ID: 050_tagging_expansion
Revises: 049_readout_data_wellless_unique
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "050_tagging_expansion"
down_revision = "049_readout_data_wellless_unique"


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


_VIEW_SQL = """
    CREATE VIEW tag_links_all AS
        SELECT 'Molecule' AS entity_type, molecule_id AS entity_id,
               tag_id, assigned_by, assigned_at FROM molecule_tags
        UNION ALL
        SELECT 'Protocol', protocol_id, tag_id, assigned_by, assigned_at FROM protocol_tags
        UNION ALL
        SELECT 'Project', project_id, tag_id, assigned_by, assigned_at FROM project_tags
        UNION ALL
        SELECT 'Collection', collection_id, tag_id, assigned_by, assigned_at FROM collection_tags
        UNION ALL
        SELECT 'Run', run_id, tag_id, assigned_by, assigned_at FROM run_tags
        UNION ALL
        SELECT 'Campaign', campaign_id, tag_id, assigned_by, assigned_at FROM campaign_tags
        UNION ALL
        SELECT 'Batch', batch_id, tag_id, assigned_by, assigned_at FROM batch_tags
        UNION ALL
        SELECT 'Plate', registered_plate_id, tag_id, assigned_by, assigned_at
               FROM registered_plate_tags
"""

_VIEW_SQL_OLD = """
    CREATE VIEW tag_links_all AS
        SELECT 'Molecule' AS entity_type, molecule_id AS entity_id,
               tag_id, assigned_by, assigned_at FROM molecule_tags
        UNION ALL
        SELECT 'Protocol', protocol_id, tag_id, assigned_by, assigned_at FROM protocol_tags
        UNION ALL
        SELECT 'Project', project_id, tag_id, assigned_by, assigned_at FROM project_tags
        UNION ALL
        SELECT 'Collection', collection_id, tag_id, assigned_by, assigned_at FROM collection_tags
"""


def upgrade() -> None:
    _create_link_table("run_tags", "run_id", "runs")
    _create_link_table("campaign_tags", "campaign_id", "campaign")
    _create_link_table("batch_tags", "batch_id", "batches")
    _create_link_table("registered_plate_tags", "registered_plate_id", "registered_plates")
    op.execute("DROP VIEW IF EXISTS tag_links_all")
    op.execute(_VIEW_SQL)


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS tag_links_all")
    op.execute(_VIEW_SQL_OLD)
    op.drop_table("registered_plate_tags")
    op.drop_table("batch_tags")
    op.drop_table("campaign_tags")
    op.drop_table("run_tags")
