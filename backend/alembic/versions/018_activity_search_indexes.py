"""Activity search indexes for screening-chemistry bridge.

Revision ID: 018
Revises: 017
"""

from alembic import op

revision = "018"
down_revision = "017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_readout_data_molecule_definition",
        "readout_data",
        ["workspace_id", "molecule_id", "readout_definition_id"],
        postgresql_where="is_outlier = false",
    )
    op.create_index(
        "ix_drc_molecule_protocol",
        "dose_response_curves",
        ["workspace_id", "molecule_id", "protocol_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_drc_molecule_protocol", table_name="dose_response_curves")
    op.drop_index("ix_readout_data_molecule_definition", table_name="readout_data")
