"""Make readout_data.molecule_id and batch_id nullable for control wells.

Control wells (positive/negative) don't have compounds assigned.
Their readout data is needed for normalization and Z-prime QC.

Revision ID: 005
Revises: 004
"""
from alembic import op

revision = "005"
down_revision = "004"


def upgrade() -> None:
    op.alter_column("readout_data", "molecule_id", nullable=True)
    op.alter_column("readout_data", "batch_id", nullable=True)


def downgrade() -> None:
    op.alter_column("readout_data", "molecule_id", nullable=False)
    op.alter_column("readout_data", "batch_id", nullable=False)
