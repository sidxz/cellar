"""A campaign cell carries a person's QC verdict, replacing the computed qc_pass flag."""

import sqlalchemy as sa
from alembic import op

revision = "113_campaign_cell_qc_verdict"
down_revision = "112_campaign_managed_by"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column("campaign_measurement", "qc_pass")
    op.add_column("campaign_measurement", sa.Column("qc_verdict", sa.String(16), nullable=True))
    op.add_column("campaign_measurement", sa.Column("qc_verdict_by", sa.Uuid(), nullable=True))
    op.add_column(
        "campaign_measurement",
        sa.Column("qc_verdict_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column("campaign_measurement", sa.Column("qc_verdict_note", sa.Text(), nullable=True))
    op.create_check_constraint(
        "ck_campaign_measurement_qc_verdict",
        "campaign_measurement",
        "qc_verdict IN ('verified','failed')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_campaign_measurement_qc_verdict", "campaign_measurement", type_="check")
    op.drop_column("campaign_measurement", "qc_verdict_note")
    op.drop_column("campaign_measurement", "qc_verdict_at")
    op.drop_column("campaign_measurement", "qc_verdict_by")
    op.drop_column("campaign_measurement", "qc_verdict")
    op.add_column("campaign_measurement", sa.Column("qc_pass", sa.Boolean(), nullable=True))
