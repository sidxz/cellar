"""Add intercept_values JSONB column to dose_response_curves.

CDD-parity multi-intercept support — one Hill fit can carry IC50 + IC90
+ IC99 (or EC50 + EC90 etc.) computed from the same parameters. Legacy
single-intercept rows leave the column NULL; readers synthesize a
single-element list from ``(curve_type, fitted_value, ci_low, ci_high)``
when None, so no data backfill is needed.

Revision ID: 022
Revises: 021
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "022"
down_revision = "021"


def upgrade() -> None:
    op.add_column(
        "dose_response_curves",
        sa.Column("intercept_values", JSONB, nullable=True),
    )


def downgrade() -> None:
    op.drop_column("dose_response_curves", "intercept_values")
