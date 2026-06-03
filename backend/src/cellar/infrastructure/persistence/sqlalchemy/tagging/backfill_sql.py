"""Backfill the legacy ``molecules.tags`` strings into the tag registry +
``molecule_tags`` links. Shared by migration 047 and its test.

Implemented in Python (not pure SQL) so the normalized key is computed with
``str.strip().casefold()`` — byte-for-byte identical to the runtime domain
(``TagName.normalized_key``). A SQL ``lower()`` would diverge from ``casefold()``
on non-ASCII keys (e.g. German ``ß`` → ``ss``), which would let a later
``get_or_create`` insert a duplicate tag for the same display string and defeat
the case-insensitive identity invariant.

The backfill is idempotent (``ON CONFLICT DO NOTHING`` on both the unique tag
index and the link composite PK). ``molecules.tags`` (a JSON array of strings)
still exists until migration 048 drops it.

Note: ``molecules`` has no ``created_by`` column, so a sentinel zero UUID marks
backfilled rows as system-migrated.
"""

from __future__ import annotations

import json
import uuid

import sqlalchemy as sa
from sqlalchemy.engine import Connection

# Sentinel UUID used as created_by/assigned_by for backfilled rows.
_SYSTEM_UUID = uuid.UUID("00000000-0000-0000-0000-000000000000")


def _normalize_key(raw: str) -> str:
    """Mirror ``TagName`` key normalization exactly (strip + casefold)."""
    return raw.strip().casefold()


def backfill_molecule_tags(conn: Connection) -> None:
    """Migrate legacy ``molecules.tags`` into ``tags`` + ``molecule_tags``.

    Idempotent: safe to re-run. The earliest-created molecule's casing wins as
    the canonical display key for each normalized (workspace, key).
    """
    rows = conn.execute(
        sa.text(
            "SELECT id, workspace_id, tags, created_at "
            "FROM molecules "
            "WHERE tags IS NOT NULL "
            "ORDER BY created_at, id"
        )
    ).all()

    # (workspace_id, normalized_key) -> canonical display key (first seen wins).
    canonical: dict[tuple[uuid.UUID, str], str] = {}
    # Per-molecule (mol_id, workspace_id, normalized_key, created_at) link rows.
    links: list[tuple[uuid.UUID, uuid.UUID, str, object]] = []

    for mol_id, workspace_id, tags, created_at in rows:
        # A JSON column may arrive already decoded (psycopg2) or as raw text
        # (some drivers); normalize to a Python value before inspecting it.
        if isinstance(tags, str):
            try:
                tags = json.loads(tags)
            except ValueError:
                continue
        if not isinstance(tags, list):
            continue
        for elem in tags:
            if not isinstance(elem, str):
                continue
            display = elem.strip()
            if not display:
                continue
            norm = _normalize_key(elem)
            key = (workspace_id, norm)
            canonical.setdefault(key, display)
            links.append((mol_id, workspace_id, norm, created_at))

    if not canonical:
        return

    insert_tag = sa.text(
        "INSERT INTO tags "
        "(id, workspace_id, key, value, normalized_key, normalized_value, "
        " created_by, created_at, updated_at, version) "
        "VALUES (:id, :workspace_id, :key, NULL, :normalized_key, NULL, "
        "        :created_by, now(), now(), 1) "
        "ON CONFLICT (workspace_id, normalized_key, normalized_value) DO NOTHING"
    )
    for (workspace_id, norm), display in canonical.items():
        conn.execute(
            insert_tag,
            {
                "id": uuid.uuid4(),
                "workspace_id": workspace_id,
                "key": display,
                "normalized_key": norm,
                "created_by": _SYSTEM_UUID,
            },
        )

    # Resolve canonical tag ids (value-less tags) for every workspace touched.
    tag_id_by_key: dict[tuple[uuid.UUID, str], uuid.UUID] = {}
    workspace_ids = list({ws for ws, _ in canonical})
    tag_rows = conn.execute(
        sa.text(
            "SELECT id, workspace_id, normalized_key FROM tags "
            "WHERE normalized_value IS NULL AND workspace_id = ANY(:ws)"
        ),
        {"ws": workspace_ids},
    ).all()
    for tag_id, workspace_id, norm in tag_rows:
        tag_id_by_key[(workspace_id, norm)] = tag_id

    insert_link = sa.text(
        "INSERT INTO molecule_tags (molecule_id, tag_id, assigned_by, assigned_at) "
        "VALUES (:molecule_id, :tag_id, :assigned_by, :assigned_at) "
        "ON CONFLICT (molecule_id, tag_id) DO NOTHING"
    )
    for mol_id, workspace_id, norm, created_at in links:
        tag_id = tag_id_by_key.get((workspace_id, norm))
        if tag_id is None:
            continue
        conn.execute(
            insert_link,
            {
                "molecule_id": mol_id,
                "tag_id": tag_id,
                "assigned_by": _SYSTEM_UUID,
                "assigned_at": created_at,
            },
        )
