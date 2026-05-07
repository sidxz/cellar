"""Add fit_quality_warnings JSONB to dose_response_curves.

Phase A of the dose-response fit refactor surfaces fit-quality issues
(EC50 hit a parameter bound, fitted IC50 outside the tested dose range,
low R²) as a list of machine-readable codes the frontend turns into
amber badges. NULL is allowed; legacy curves treat None as no warnings.

Revision ID: 020
Revises: 019
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "020"
down_revision = "019"


def upgrade() -> None:
    op.add_column(
        "dose_response_curves",
        sa.Column("fit_quality_warnings", JSONB, nullable=True),
    )


def downgrade() -> None:
    op.drop_column("dose_response_curves", "fit_quality_warnings")
