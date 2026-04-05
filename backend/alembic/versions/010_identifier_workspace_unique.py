"""Add workspace_id to molecule_identifiers and fix unique constraint.

The design mandates UNIQUE(workspace_id, identifier) but the table only had
UNIQUE(molecule_id, identifier), allowing the same identifier on different
molecules. This migration adds workspace_id (backfilled from the parent
molecules table) and replaces the constraint.

Revision ID: 010
Revises: 009
Create Date: 2026-04-04
"""

import sqlalchemy as sa
from alembic import op

revision: str = "010"
down_revision: str = "009"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    # 1. Pre-check: detect any existing cross-molecule duplicate identifiers
    conn = op.get_bind()
    dupes = conn.execute(
        sa.text("""
            SELECT mi.identifier, m.workspace_id, COUNT(DISTINCT mi.molecule_id) AS cnt
            FROM molecule_identifiers mi
            JOIN molecules m ON m.id = mi.molecule_id
            WHERE m.merged_into_id IS NULL
            GROUP BY mi.identifier, m.workspace_id
            HAVING COUNT(DISTINCT mi.molecule_id) > 1
        """)
    ).fetchall()
    if dupes:
        dup_list = ", ".join(f"'{d[0]}'" for d in dupes[:10])
        raise RuntimeError(
            f"Cannot add workspace-unique constraint: {len(dupes)} identifier(s) "
            f"are shared across multiple molecules in the same workspace: {dup_list}. "
            f"Resolve duplicates before running this migration."
        )

    # 2. Add workspace_id column (nullable initially)
    op.add_column(
        "molecule_identifiers",
        sa.Column("workspace_id", sa.Uuid(), nullable=True),
    )

    # 3. Backfill from parent molecules table
    op.execute(
        sa.text("""
            UPDATE molecule_identifiers mi
            SET workspace_id = m.workspace_id
            FROM molecules m
            WHERE mi.molecule_id = m.id
        """)
    )

    # 4. Make NOT NULL
    op.alter_column("molecule_identifiers", "workspace_id", nullable=False)

    # 5. Drop old constraint
    op.drop_constraint("uq_mol_ident", "molecule_identifiers", type_="unique")

    # 6. Create new workspace-scoped unique constraint
    op.create_unique_constraint(
        "uq_ws_identifier", "molecule_identifiers", ["workspace_id", "identifier"]
    )

    # 7. Index for workspace_id lookups
    op.create_index(
        "ix_mol_ident_workspace", "molecule_identifiers", ["workspace_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_mol_ident_workspace", table_name="molecule_identifiers")
    op.drop_constraint("uq_ws_identifier", "molecule_identifiers", type_="unique")
    op.create_unique_constraint(
        "uq_mol_ident", "molecule_identifiers", ["molecule_id", "identifier"]
    )
    op.drop_column("molecule_identifiers", "workspace_id")
