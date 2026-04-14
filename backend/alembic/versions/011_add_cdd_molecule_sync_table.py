"""Add cdd_molecule_sync table for tracking CDD-to-local molecule mappings.

Revision ID: 011
Revises: 010
"""

import sqlalchemy as sa
from alembic import op

revision = "011"
down_revision = "010"


def upgrade() -> None:
    op.create_table(
        "cdd_molecule_sync",
        sa.Column(
            "id",
            sa.Uuid(),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("cdd_vault_id", sa.String(50), nullable=False),
        sa.Column("cdd_molecule_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "molecule_id",
            sa.Uuid(),
            sa.ForeignKey("molecules.id"),
            nullable=False,
        ),
        sa.Column("cdd_modified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "last_synced_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "workspace_id",
            "cdd_vault_id",
            "cdd_molecule_id",
            name="uq_cdd_sync_ws_vault_mol",
        ),
    )
    op.create_index(
        "ix_cdd_mol_sync_ws_vault",
        "cdd_molecule_sync",
        ["workspace_id", "cdd_vault_id"],
    )
    op.create_index(
        "ix_cdd_mol_sync_molecule",
        "cdd_molecule_sync",
        ["molecule_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_cdd_mol_sync_molecule", table_name="cdd_molecule_sync")
    op.drop_index("ix_cdd_mol_sync_ws_vault", table_name="cdd_molecule_sync")
    op.drop_table("cdd_molecule_sync")
