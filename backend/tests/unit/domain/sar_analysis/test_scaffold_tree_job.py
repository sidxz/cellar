from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

from cellar.domain.sar_analysis.scaffold_tree_job import ScaffoldTreeJob
from cellar.domain.sar_analysis.scaffold_tree_types import (
    ScaffoldTreeResult,
    ScaffoldTreeStats,
)
from cellar.domain.shared.async_job import AsyncJobStatus, InvalidJobTransition

_NOW = datetime(2026, 5, 17, tzinfo=timezone.utc)
_LATER = datetime(2026, 5, 17, 0, 1, tzinfo=timezone.utc)
_LATEST = datetime(2026, 5, 17, 0, 2, tzinfo=timezone.utc)


def _new_job() -> ScaffoldTreeJob:
    return ScaffoldTreeJob.create(
        workspace_id=uuid.uuid4(),
        requested_by=uuid.uuid4(),
        ids_hash="abc",
        now=_NOW,
    )


def _minimal_result() -> ScaffoldTreeResult:
    return ScaffoldTreeResult(
        nodes=[],
        edges=[],
        stats=ScaffoldTreeStats(node_count=0, elapsed_ms=10, cache_hit=False),
    )


def test_create_starts_in_pending_status():
    job = _new_job()
    assert job.status == AsyncJobStatus.PENDING
    assert job.started_at is None
    assert job.result is None


def test_running_to_ready():
    job = _new_job()
    job.mark_running(_LATER)
    result = _minimal_result()
    job.mark_ready(result=result, now=_LATEST)
    assert job.status == AsyncJobStatus.READY
    assert job.result is result
    assert job.completed_at == _LATEST


def test_cannot_mark_ready_from_pending():
    job = _new_job()
    with pytest.raises(InvalidJobTransition):
        job.mark_ready(result=_minimal_result(), now=_LATER)
