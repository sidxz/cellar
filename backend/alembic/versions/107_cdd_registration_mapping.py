"""107 — the CDD data source carries a registration mapping.

Adds ``data_sources.registration_mapping`` (JSONB, NULL) and converts each
``cdd_vault`` source's molecule/batch ``field_mappings`` into it (phase-1 shape:
``{header, target, source, separator}``; ``header`` = vault field path, batch fields
prefixed ``batch.``). The two ``field_mappings`` are then emptied; plate and well
mappings are untouched. A source that already has a registration mapping is skipped.

Conversion (an admin's own mappings are kept, what has no target is dropped):
  core name/smiles/molecule_type, amount_value/unit, purity, appearance, salt_stoichiometry
    -> the same target; core salt_name -> salt_code;
  identifier -> compound_id (batch level: batch_id), Source = last path segment
    (the default ``synonyms`` -> "CDD synonym");
  core vendor_catalog_number -> batch_id "CDD batch ID" (first path alternative);
  ``modified_at`` (read as a fixed field by the importer) and anything else -> dropped.
A single-valued target already taken is dropped too.

Also stores the numeric vault batch id (``custom_fields.cdd_batch_id``) as a
``BatchIdentifier(type="cdd_batch_id", source="CDD import")`` where the batch lacks
it and the text is not already a batch ID in its workspace. Never reads the vault.
Downgrade drops the column (the backfilled batch IDs are correct data and stay).
"""

from __future__ import annotations

import json

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "107_cdd_registration_mapping"
down_revision = "106_bulk_registration_mappings"
branch_labels = None
depends_on = None

_SAME = {
    "molecule": {"name", "smiles", "molecule_type"},
    "batch": {"amount_value", "amount_unit", "purity", "appearance", "salt_stoichiometry"},
}
_MULTI = {"compound_id", "batch_id"}


def _col(header: str, target: str, source: str | None = None) -> dict:
    return {"header": header, "target": target, "source": source, "separator": None}


def _label(path: str) -> str:
    return "CDD synonym" if path == "synonyms" else path.split("|")[0].split(".")[-1]


def _convert(entity_mappings: list[dict]) -> list[dict]:
    cols: list[dict] = []
    taken: set[str] = set()
    for em in entity_mappings:
        level = em.get("entity_type")
        if level not in ("molecule", "batch"):
            continue
        prefix = "batch." if level == "batch" else ""
        for fm in em.get("field_mappings") or []:
            path, tfield, ttype = fm["source_field"], fm["target_field"], fm["target_type"]
            header = "|".join(prefix + p for p in path.split("|"))
            if ttype == "identifier":
                col = _col(header, "batch_id" if level == "batch" else "compound_id", _label(path))
            elif ttype == "core" and level == "batch" and tfield == "vendor_catalog_number":
                col = _col(prefix + path.split("|")[0], "batch_id", "CDD batch ID")
            elif ttype == "core" and tfield == "salt_name" and level == "batch":
                col = _col(header, "salt_code")
            elif ttype == "core" and tfield in _SAME[level]:
                col = _col(header, tfield)
            else:
                continue  # modified_at, custom fields, unknown targets
            if col["target"] not in _MULTI:
                if col["target"] in taken:
                    continue
                taken.add(col["target"])
            cols.append(col)
    return cols


def upgrade() -> None:
    op.add_column(
        "data_sources", sa.Column("registration_mapping", postgresql.JSONB(), nullable=True)
    )
    convert_sources()
    backfill_cdd_batch_ids()


def convert_sources() -> None:
    conn = op.get_bind()
    rows = conn.execute(
        sa.text(
            "SELECT id, entity_mappings FROM data_sources "
            "WHERE source_type = 'cdd_vault' AND registration_mapping IS NULL"
        )
    ).all()
    for ds_id, mappings in rows:
        mappings = mappings or []
        kept = [
            {**em, "field_mappings": []} if em.get("entity_type") in ("molecule", "batch") else em
            for em in mappings
        ]
        conn.execute(
            sa.text(
                "UPDATE data_sources SET registration_mapping = CAST(:rm AS jsonb), "
                "entity_mappings = CAST(:em AS jsonb) WHERE id = :id"
            ),
            {"rm": json.dumps(_convert(mappings)), "em": json.dumps(kept), "id": ds_id},
        )


def backfill_cdd_batch_ids() -> None:
    op.execute(
        """
        INSERT INTO batch_identifiers (
            id, batch_id, workspace_id, identifier, identifier_type, source,
            registered_by, derived_from_molecule_identifier_id, created_at, updated_at
        )
        SELECT gen_random_uuid(), b.id, b.workspace_id, trim(b.custom_fields ->> 'cdd_batch_id'),
               'cdd_batch_id', 'CDD import', b.chemist, NULL, now(), now()
        FROM batches b
        WHERE coalesce(trim(b.custom_fields ->> 'cdd_batch_id'), '') <> ''
          AND NOT EXISTS (
              SELECT 1 FROM batch_identifiers x
              WHERE x.workspace_id = b.workspace_id
                AND x.identifier = trim(b.custom_fields ->> 'cdd_batch_id')
          )
        ON CONFLICT (workspace_id, identifier) DO NOTHING
        """
    )


def downgrade() -> None:
    op.drop_column("data_sources", "registration_mapping")
