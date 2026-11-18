"""105 — batches from the CDD automated import keep their CDD batch name as a real ID.

The CDD automated import stored the vault's batch name (``SACC-0013250-001``) only
in ``batches.vendor_catalog_number``, plus — when the compound's name matched —
an automatic alias with the same text. Bulk Registration now matches a row to an
existing batch by real IDs only (automatic aliases never match), so without this
an overlapping file export would create those batches a second time.

For every batch with ``custom_fields.cdd_batch_id`` and a non-empty
``vendor_catalog_number``:
  1. an automatic alias with exactly that text on the same batch becomes a real ID
     (``derived_from_molecule_identifier_id = NULL``, source ``CDD batch ID``);
  2. otherwise, when no batch ID in the workspace has that text, one is inserted
     (type ``custom``, source ``CDD batch ID``, registered by the batch's chemist);
  3. otherwise (text already used elsewhere, or on two CDD batches) nothing happens.

``vendor_catalog_number`` is left as is. Idempotent. Downgrade is a no-op: the IDs
are correct data, and step 1 cannot be told apart from a person's edit afterwards.
"""

from __future__ import annotations

from alembic import op

revision = "105_cdd_batch_name_backfill"
down_revision = "104_stage_owned_campaign_values"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.execute(
        """
        UPDATE batch_identifiers bi
        SET derived_from_molecule_identifier_id = NULL,
            source = 'CDD batch ID',
            updated_at = now()
        FROM batches b
        WHERE bi.batch_id = b.id
          AND (b.custom_fields ->> 'cdd_batch_id') IS NOT NULL
          AND coalesce(trim(b.vendor_catalog_number), '') <> ''
          AND bi.identifier = trim(b.vendor_catalog_number)
          AND bi.derived_from_molecule_identifier_id IS NOT NULL
        """
    )
    op.execute(
        """
        INSERT INTO batch_identifiers (
            id, batch_id, workspace_id, identifier, identifier_type, source,
            registered_by, derived_from_molecule_identifier_id, created_at, updated_at
        )
        SELECT gen_random_uuid(), b.id, b.workspace_id, trim(b.vendor_catalog_number),
               'custom', 'CDD batch ID', b.chemist, NULL, now(), now()
        FROM batches b
        WHERE (b.custom_fields ->> 'cdd_batch_id') IS NOT NULL
          AND coalesce(trim(b.vendor_catalog_number), '') <> ''
          AND NOT EXISTS (
              SELECT 1 FROM batch_identifiers x
              WHERE x.workspace_id = b.workspace_id
                AND x.identifier = trim(b.vendor_catalog_number)
          )
          -- two CDD batches with the same text: which one it names is unknown, skip both
          AND NOT EXISTS (
              SELECT 1 FROM batches b2
              WHERE b2.workspace_id = b.workspace_id
                AND b2.id <> b.id
                AND (b2.custom_fields ->> 'cdd_batch_id') IS NOT NULL
                AND trim(b2.vendor_catalog_number) = trim(b.vendor_catalog_number)
          )
        """
    )


def downgrade() -> None:
    pass
