"""002 — Add readout pick_list_values, dose_response_config, and protocol control_layouts

Revision ID: 002
Revises: 001
Create Date: 2026-04-07

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '002'
down_revision: Union[str, None] = '001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Readout definition enrichment: pick_list values and dose-response config
    op.add_column(
        'readout_definitions',
        sa.Column('pick_list_values', postgresql.JSONB(), nullable=True),
    )
    op.add_column(
        'readout_definitions',
        sa.Column('dose_response_config', postgresql.JSONB(), nullable=True),
    )

    # Protocol control layouts: default plate templates per format
    op.add_column(
        'protocols',
        sa.Column('control_layouts', postgresql.JSONB(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('protocols', 'control_layouts')
    op.drop_column('readout_definitions', 'dose_response_config')
    op.drop_column('readout_definitions', 'pick_list_values')
