"""Frozen backfill SQL: migrate legacy ``molecules.tags`` strings into the tag
registry + ``molecule_tags`` links. Shared by migration 047 and its test.

Both statements are idempotent. They read ``molecules.tags`` (a JSON array of
strings), which still exists until migration 048 drops it.

Note: ``molecules`` has no ``created_by`` column (the mixin only provides
``id``, ``created_at``, ``updated_at``). The backfill uses a sentinel zero UUID
as ``created_by``/``assigned_by`` to mark rows as system-migrated.
"""

from __future__ import annotations

# Sentinel UUID used as created_by/assigned_by for backfilled rows,
# because molecules has no creator column.
_SYSTEM_UUID = "'00000000-0000-0000-0000-000000000000'::uuid"

# 1) One value-less tag per distinct (workspace, normalized key). DISTINCT ON
#    picks the earliest-created molecule's casing as the canonical row.
#    Guard: json_typeof = 'array' rejects SQL-NULL rows and JSON-null scalars.
BACKFILL_TAGS_SQL = f"""
INSERT INTO tags
    (id, workspace_id, key, value, normalized_key, normalized_value,
     created_by, created_at, updated_at, version)
SELECT
    gen_random_uuid(), d.workspace_id, d.key, NULL,
    lower(btrim(d.key)), NULL, {_SYSTEM_UUID}, now(), now(), 1
FROM (
    SELECT DISTINCT ON (m.workspace_id, lower(btrim(elem)))
        m.workspace_id AS workspace_id,
        btrim(elem)    AS key
    FROM molecules m
    CROSS JOIN LATERAL json_array_elements_text(m.tags) AS elem
    WHERE json_typeof(m.tags) = 'array' AND btrim(elem) <> ''
    ORDER BY m.workspace_id, lower(btrim(elem)), m.created_at
) d
ON CONFLICT (workspace_id, normalized_key, normalized_value) DO NOTHING;
"""

# 2) One link per (molecule, tag string), joined back to the canonical tag row.
BACKFILL_LINKS_SQL = f"""
INSERT INTO molecule_tags (molecule_id, tag_id, assigned_by, assigned_at)
SELECT m.id, t.id, {_SYSTEM_UUID}, m.created_at
FROM molecules m
CROSS JOIN LATERAL json_array_elements_text(m.tags) AS elem
JOIN tags t
    ON t.workspace_id = m.workspace_id
   AND t.normalized_key = lower(btrim(elem))
   AND t.normalized_value IS NULL
WHERE json_typeof(m.tags) = 'array' AND btrim(elem) <> ''
ON CONFLICT (molecule_id, tag_id) DO NOTHING;
"""
