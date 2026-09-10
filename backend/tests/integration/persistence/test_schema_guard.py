"""The real migrated test database is at this image's head (proves the SELECT path)."""

from __future__ import annotations

from cellar.infrastructure.persistence.schema_guard import (
    database_revision,
    ensure_schema_current,
    expected_head,
)


async def test_migrated_database_reads_as_current(session_factory) -> None:
    assert await database_revision(session_factory) == expected_head()
    assert await ensure_schema_current(session_factory, wait_seconds=0) == expected_head()
