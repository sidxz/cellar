"""Add description column to readout_definitions.

Pure additive — nullable text column for documenting what a readout
captures. Cosmetic field per the graduated-mutability model: editable
on unlocked ACTIVE protocols (no run-data interpretation depends on
it). Existing rows default to NULL ("no description").

Revision ID: 024
Revises: 023
"""

import sqlalchemy as sa
from alembic import op

revision = "024"
down_revision = "023"


def upgrade() -> None:
    op.add_column(
        "readout_definitions",
        sa.Column("description", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("readout_definitions", "description")
