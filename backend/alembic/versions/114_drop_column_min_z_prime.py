"""A campaign column no longer filters runs by Z': strip min_z_prime from stored filters.

``campaign_channel.qc_filter`` is JSONB. A filter left with nothing meaningful (an empty
object, or only ``require_approved: false``) becomes NULL.

Closed and superseded campaigns are left alone: their stored filter records how their
frozen values were picked, and no compliance trigger is disabled to rewrite them.

Downgrade is a no-op: the removed values cannot be restored.
"""

import sqlalchemy as sa
from alembic import op

revision = "114_drop_column_min_z_prime"
down_revision = "113_campaign_cell_qc_verdict"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        sa.text(
            "UPDATE campaign_channel SET qc_filter = qc_filter - 'min_z_prime' "
            "WHERE qc_filter ? 'min_z_prime' "
            "AND campaign_id NOT IN (SELECT id FROM campaign "
            "WHERE status IN ('closed','superseded'))"
        )
    )
    op.execute(
        sa.text(
            "UPDATE campaign_channel SET qc_filter = NULL WHERE qc_filter IS NOT NULL "
            "AND (qc_filter = '{}'::jsonb OR qc_filter = '{\"require_approved\": false}'::jsonb) "
            "AND campaign_id NOT IN (SELECT id FROM campaign "
            "WHERE status IN ('closed','superseded'))"
        )
    )


def downgrade() -> None:
    pass
