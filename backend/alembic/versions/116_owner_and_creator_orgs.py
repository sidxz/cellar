"""Collections, projects and protocols record the creator's Duar org and an owner org.

Orgs live in Duar, so these are plain uuid columns with no FK. A collection's
``owned_by_org_id`` (an FK to Cellar's local org list) becomes ``owner_org_id`` and
loses its FK. Schema only: ``scripts/backfill_duar_orgs.py`` fills existing rows
with one Duar org named by the operator.
"""

import sqlalchemy as sa
from alembic import op

revision = "116_owner_and_creator_orgs"
down_revision = "115_campaign_result_note_stamp"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("collections_owned_by_org_id_fkey", "collections", type_="foreignkey")
    op.alter_column("collections", "owned_by_org_id", new_column_name="owner_org_id")
    op.add_column("collections", sa.Column("created_by_org_id", sa.Uuid(), nullable=True))
    for table in ("projects", "protocols"):
        op.add_column(table, sa.Column("created_by_org_id", sa.Uuid(), nullable=True))
        op.add_column(table, sa.Column("owner_org_id", sa.Uuid(), nullable=True))


def downgrade() -> None:
    for table in ("protocols", "projects"):
        op.drop_column(table, "owner_org_id")
        op.drop_column(table, "created_by_org_id")
    op.drop_column("collections", "created_by_org_id")
    op.alter_column("collections", "owner_org_id", new_column_name="owned_by_org_id")
    # Duar ids may now sit in the column; they can't satisfy the old FK.
    op.execute("UPDATE collections SET owned_by_org_id = NULL")
    op.create_foreign_key(
        "collections_owned_by_org_id_fkey",
        "collections",
        "organizations",
        ["owned_by_org_id"],
        ["id"],
        ondelete="SET NULL",
    )
