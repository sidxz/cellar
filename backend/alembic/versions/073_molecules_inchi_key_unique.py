"""073 — unique active InChIKey per workspace

RegisterMolecule dedups by InChIKey in application code, but the only index on
(workspace_id, inchi_key) was non-unique, so two concurrent registrations of
the same structure both passed the read and both inserted. Once that happens,
find_by_inchi_key's scalar_one_or_none() raises on every later registration
of that key. Partial: a merged source keeps its inchi_key (only merged_into_id
is set) and an undisclosed molecule has none, so only live disclosed rows are
constrained — the same predicate find_by_inchi_key already filters on.

Fails loudly if duplicates already exist. Find them with

    SELECT workspace_id, inchi_key, count(*) FROM molecules
    WHERE merged_into_id IS NULL AND inchi_key IS NOT NULL
    GROUP BY 1, 2 HAVING count(*) > 1;

and merge them through the app before upgrading.

Revision ID: 073_molecules_inchi_key_unique
Revises: 072_registration_provenance
"""

import sqlalchemy as sa
from alembic import op

revision = "073_molecules_inchi_key_unique"
down_revision = "072_registration_provenance"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "uq_molecules_ws_inchi_active",
        "molecules",
        ["workspace_id", "inchi_key"],
        unique=True,
        postgresql_where=sa.text("merged_into_id IS NULL AND inchi_key IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_molecules_ws_inchi_active", table_name="molecules")
