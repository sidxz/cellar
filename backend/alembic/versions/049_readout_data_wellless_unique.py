"""049 — enforce one well-less raw readout row per summary key.

The summary-results import (well-less ``readout_data`` rows: ``well_id IS NULL``,
``is_computed = false``) upserts with latest-wins semantics. Without a uniqueness
guarantee, two imports for the same (run, molecule, batch, readout_definition)
leave duplicate rows, which both corrupts the data and makes the upsert lookup
(``find_wellless_by_keys``) ambiguous.

This adds a partial unique index over the summary key with ``NULLS NOT DISTINCT``
(PostgreSQL 15+) so a NULL ``molecule_id``/``batch_id`` collapses like any other
value. Any pre-existing duplicates are deduped first (keeping the most recent
row) so index creation cannot fail.

Revision ID: 049_readout_data_wellless_unique
Revises: 048_drop_molecules_tags
"""

from __future__ import annotations

from alembic import op

revision = "049_readout_data_wellless_unique"
down_revision = "048_drop_molecules_tags"

_DEDUP_SQL = """
DELETE FROM readout_data rd
USING (
    SELECT id,
           row_number() OVER (
               PARTITION BY workspace_id, run_id, molecule_id, batch_id,
                            readout_definition_id
               ORDER BY created_at DESC, id DESC
           ) AS rn
    FROM readout_data
    WHERE well_id IS NULL AND is_computed = false
) dup
WHERE rd.id = dup.id AND dup.rn > 1;
"""

_CREATE_INDEX_SQL = """
CREATE UNIQUE INDEX uq_readout_data_wellless ON readout_data
    (workspace_id, run_id, molecule_id, batch_id, readout_definition_id)
    NULLS NOT DISTINCT
    WHERE well_id IS NULL AND is_computed = false;
"""


def upgrade() -> None:
    op.execute(_DEDUP_SQL)
    op.execute(_CREATE_INDEX_SQL)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_readout_data_wellless")
