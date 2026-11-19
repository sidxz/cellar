"""109 — an index for case-insensitive compound ID lookups.

Compound IDs are matched ignoring case (``lower(identifier)``: identifier holders, the
undisclosed match, ``find_by_identifier``), which the unique key on ``identifier`` can't
serve. Plain CREATE INDEX (fine at dev size). On a large production table build it first,
without locking writes, with ``CREATE INDEX CONCURRENTLY`` (same name and columns) outside
a transaction; this migration then finds it and does nothing.
"""

from __future__ import annotations

from alembic import op

revision = "109_molecule_ident_lower_idx"  # alembic_version holds 32 characters
down_revision = "108_cdd_import_report"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_molecule_identifiers_ws_lower_identifier "
        "ON molecule_identifiers (workspace_id, lower(identifier))"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_molecule_identifiers_ws_lower_identifier")
