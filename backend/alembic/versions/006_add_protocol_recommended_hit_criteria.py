"""Add protocol recommended_hit_criteria column.

Stores recommended hit filter rules (up to 3 AND-conditions) as JSONB
for the protocol detail page Activity tab.

Revision ID: 006
Revises: 005
"""

import sqlalchemy as sa
from alembic import op

revision = "006"
down_revision = "005"


def upgrade() -> None:
    op.add_column(
        "protocols",
        sa.Column("recommended_hit_criteria", sa.dialects.postgresql.JSONB(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("protocols", "recommended_hit_criteria")
