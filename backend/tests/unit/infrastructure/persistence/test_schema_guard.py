"""Startup schema guard: refuse to serve against a database not at this image's head."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from cellar.infrastructure.persistence.schema_guard import (
    SchemaOutOfDate,
    ensure_schema_current,
    expected_head,
)

VERSIONS = Path(__file__).resolve().parents[4] / "alembic" / "versions"


def _latest_migration_file() -> str:
    return max(p.stem for p in VERSIONS.glob("[0-9]*.py"))


class TestExpectedHead:
    def test_is_the_newest_migration_script(self) -> None:
        assert expected_head() == _latest_migration_file()


class TestEnsureSchemaCurrent:
    async def test_at_head_returns_immediately(self) -> None:
        head = expected_head()
        read = AsyncMock(return_value=head)
        assert await ensure_schema_current(None, wait_seconds=0, read_revision=read) == head
        read.assert_awaited_once()

    async def test_behind_refuses_and_names_both_revisions(self) -> None:
        read = AsyncMock(return_value="071_shipment_container")
        with pytest.raises(SchemaOutOfDate) as exc:
            await ensure_schema_current(None, wait_seconds=0, read_revision=read)
        msg = str(exc.value)
        assert "071_shipment_container" in msg
        assert expected_head() in msg
        assert "alembic upgrade head" in msg
        assert "pending" in msg.lower()

    async def test_empty_database_counts_as_behind(self) -> None:
        read = AsyncMock(return_value=None)
        with pytest.raises(SchemaOutOfDate, match="no migrations"):
            await ensure_schema_current(None, wait_seconds=0, read_revision=read)

    async def test_unknown_revision_means_database_is_ahead_of_this_image(self) -> None:
        read = AsyncMock(return_value="999_from_the_future")
        with pytest.raises(SchemaOutOfDate, match="ahead"):
            await ensure_schema_current(None, wait_seconds=0, read_revision=read)

    async def test_waits_for_a_migrate_job_that_finishes_in_time(self) -> None:
        head = expected_head()
        read = AsyncMock(side_effect=["071_shipment_container", "071_shipment_container", head])
        out = await ensure_schema_current(
            None, wait_seconds=5, poll_seconds=0.01, read_revision=read
        )
        assert out == head
        assert read.await_count == 3

    async def test_gives_up_after_the_wait_window(self) -> None:
        read = AsyncMock(return_value="071_shipment_container")
        with pytest.raises(SchemaOutOfDate):
            await ensure_schema_current(
                None, wait_seconds=0.05, poll_seconds=0.01, read_revision=read
            )
        assert read.await_count >= 2
