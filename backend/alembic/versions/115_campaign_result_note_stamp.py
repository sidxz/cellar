"""A campaign row's note records who last saved it and when.

Existing notes keep a null author and time: nothing is invented for them.
"""

import sqlalchemy as sa
from alembic import op

revision = "115_campaign_result_note_stamp"
down_revision = "114_drop_column_min_z_prime"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("campaign_result", sa.Column("notes_edited_by", sa.Uuid(), nullable=True))
    op.add_column(
        "campaign_result",
        sa.Column("notes_edited_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("campaign_result", "notes_edited_at")
    op.drop_column("campaign_result", "notes_edited_by")
