"""A campaign row's note records who last saved it, when, and how many versions it has,
on any campaign status.

Existing notes keep a null author and time: nothing is invented for them. They
count as one version (the history lists them as the note from before tracking).

Notes can be saved on closed and superseded campaigns too (owner ruling
2026-11-21), so the lock trigger on ``campaign_result`` (migration 027) is split:
inserts and deletes stay refused as before, and an UPDATE is refused unless the
only columns it changes are the note's own (``notes``, ``notes_edited_by``,
``notes_edited_at``, ``notes_version_count``) plus the row's ``updated_at``, which
the ORM moves on every UPDATE. Comparing the whole row minus those keeps any
column added later locked. The count's backfill runs while no lock trigger is on
the table, so a closed campaign's noted row takes its count too.
"""

import sqlalchemy as sa
from alembic import op

revision = "115_campaign_result_note_stamp"
down_revision = "114_drop_column_min_z_prime"
branch_labels = None
depends_on = None

_NOTE_COLUMNS = (
    "ARRAY['notes', 'notes_edited_by', 'notes_edited_at', 'notes_version_count', "
    "'updated_at']::text[]"
)


def upgrade() -> None:
    op.add_column("campaign_result", sa.Column("notes_edited_by", sa.Uuid(), nullable=True))
    op.add_column(
        "campaign_result",
        sa.Column("notes_edited_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "campaign_result",
        sa.Column("notes_version_count", sa.Integer(), nullable=False, server_default="0"),
    )

    op.execute("DROP TRIGGER campaign_result_reject_locked ON campaign_result;")
    op.execute("UPDATE campaign_result SET notes_version_count = 1 WHERE notes IS NOT NULL;")
    op.execute(
        """
        CREATE TRIGGER campaign_result_reject_locked
        BEFORE INSERT OR DELETE ON campaign_result
        FOR EACH ROW EXECUTE FUNCTION reject_locked_campaign_write();
        """
    )
    op.execute(
        f"""
        CREATE TRIGGER campaign_result_reject_locked_update
        BEFORE UPDATE ON campaign_result
        FOR EACH ROW
        WHEN ((to_jsonb(OLD) - {_NOTE_COLUMNS}) IS DISTINCT FROM (to_jsonb(NEW) - {_NOTE_COLUMNS}))
        EXECUTE FUNCTION reject_locked_campaign_write();
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER campaign_result_reject_locked_update ON campaign_result;")
    op.execute("DROP TRIGGER campaign_result_reject_locked ON campaign_result;")
    op.execute(
        """
        CREATE TRIGGER campaign_result_reject_locked
        BEFORE INSERT OR UPDATE OR DELETE ON campaign_result
        FOR EACH ROW EXECUTE FUNCTION reject_locked_campaign_write();
        """
    )
    op.drop_column("campaign_result", "notes_version_count")
    op.drop_column("campaign_result", "notes_edited_at")
    op.drop_column("campaign_result", "notes_edited_by")
