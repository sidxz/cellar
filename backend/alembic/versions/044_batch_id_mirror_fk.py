"""044 — auto-mirror FK on batch_identifiers.

Adds nullable FK from batch_identifiers to molecule_identifiers so that
synonyms registered on a Molecule can fan out a parallel BatchIdentifier
per batch. ON DELETE CASCADE means removing a MoleculeIdentifier
automatically removes its derived mirrors.

NULL on this column = chemist-added BatchIdentifier (untouched by sync).
Non-NULL = auto-mirror keyed to a specific MoleculeIdentifier.

Revision ID: 044_batch_id_mirror_fk
Revises: 043_batch_identifiers
Create Date: 2026-05-22
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "044_batch_id_mirror_fk"
down_revision: str | None = "043_batch_identifiers"
branch_labels: None = None
depends_on: None = None


def upgrade() -> None:
    op.add_column(
        "batch_identifiers",
        sa.Column(
            "derived_from_molecule_identifier_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("molecule_identifiers.id", ondelete="CASCADE"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_batch_identifiers_derived_from",
        "batch_identifiers",
        ["derived_from_molecule_identifier_id"],
        postgresql_where=sa.text("derived_from_molecule_identifier_id IS NOT NULL"),
    )


def downgrade() -> None:
    # Drop either name (handles re-apply after the idx_ → ix_ rename)
    op.execute(sa.text("DROP INDEX IF EXISTS ix_batch_identifiers_derived_from"))
    op.execute(sa.text("DROP INDEX IF EXISTS idx_batch_identifiers_derived_from"))
    op.drop_column("batch_identifiers", "derived_from_molecule_identifier_id")
