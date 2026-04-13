"""Add compound_flags table.

Stores team-visible flags (star, outlier, follow_up) on compounds
within a protocol. Unique constraint prevents duplicate flags per
(workspace, molecule, protocol, user, flag_type).

Revision ID: 007
Revises: 006
"""

import sqlalchemy as sa
from alembic import op

revision = "007"
down_revision = "006"


def upgrade() -> None:
    op.create_table(
        "compound_flags",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("molecule_id", sa.Uuid(), nullable=False),
        sa.Column("protocol_id", sa.Uuid(), nullable=False),
        sa.Column("flagged_by", sa.Uuid(), nullable=False),
        sa.Column("flag_type", sa.String(20), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "workspace_id",
            "molecule_id",
            "protocol_id",
            "flagged_by",
            "flag_type",
            name="uq_compound_flag_unique",
        ),
    )
    op.create_index(
        "ix_compound_flag_ws_protocol",
        "compound_flags",
        ["workspace_id", "protocol_id"],
    )
    op.create_index(
        "ix_compound_flag_ws_molecule",
        "compound_flags",
        ["workspace_id", "molecule_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_compound_flag_ws_molecule", table_name="compound_flags")
    op.drop_index("ix_compound_flag_ws_protocol", table_name="compound_flags")
    op.drop_table("compound_flags")
