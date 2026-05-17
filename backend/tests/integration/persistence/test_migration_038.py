"""Integration test: migration 038 — scaffold_tree_jobs table."""

from __future__ import annotations

import pytest
from sqlalchemy import inspect


@pytest.mark.asyncio
async def test_scaffold_tree_jobs_table_exists(engine):
    async with engine.connect() as conn:
        tables = await conn.run_sync(lambda c: inspect(c).get_table_names())
    assert "scaffold_tree_jobs" in tables


@pytest.mark.asyncio
async def test_scaffold_tree_jobs_columns(engine):
    async with engine.connect() as conn:
        cols = await conn.run_sync(
            lambda c: {col["name"]: col for col in inspect(c).get_columns("scaffold_tree_jobs")}
        )
    expected = {
        "id", "workspace_id", "requested_by", "ids_hash", "requested_at",
        "status", "started_at", "completed_at", "error_message",
        "result_json", "version",
    }
    assert expected.issubset(set(cols))
    assert cols["result_json"]["nullable"] is True
    assert str(cols["result_json"]["type"]).upper() in {"JSONB", "JSON"}


@pytest.mark.asyncio
async def test_scaffold_tree_jobs_cache_index(engine):
    async with engine.connect() as conn:
        indexes = await conn.run_sync(lambda c: inspect(c).get_indexes("scaffold_tree_jobs"))
    names = {idx["name"] for idx in indexes}
    assert "scaffold_tree_jobs_cache" in names
