from __future__ import annotations
import uuid
from datetime import datetime, timezone

import pytest

from cellar.domain.sar_analysis.scaffold_tree_job import (
    InvalidScaffoldTreeJobTransition,
    ScaffoldTreeJob,
    ScaffoldTreeJobStatus,
)
from cellar.domain.sar_analysis.scaffold_tree_types import (
    ScaffoldTreeResult,
    ScaffoldTreeStats,
)


def _new_job() -> ScaffoldTreeJob:
    return ScaffoldTreeJob.create(
        workspace_id=uuid.uuid4(),
        requested_by=uuid.uuid4(),
        ids_hash="abc",
        now=datetime(2026, 5, 17, tzinfo=timezone.utc),
    )


def test_create_starts_in_pending_status():
    job = _new_job()
    assert job.status == ScaffoldTreeJobStatus.PENDING
    assert job.started_at is None
    assert job.result is None


def test_pending_to_running():
    job = _new_job()
    now = datetime(2026, 5, 17, 0, 1, tzinfo=timezone.utc)
    running = job.mark_running(now)
    assert running.status == ScaffoldTreeJobStatus.RUNNING
    assert running.started_at == now


def test_running_to_ready():
    job = _new_job().mark_running(datetime(2026, 5, 17, 0, 1, tzinfo=timezone.utc))
    result = ScaffoldTreeResult(
        nodes=[], edges=[],
        stats=ScaffoldTreeStats(node_count=0, elapsed_ms=10, cache_hit=False),
    )
    ready = job.mark_ready(result, datetime(2026, 5, 17, 0, 2, tzinfo=timezone.utc))
    assert ready.status == ScaffoldTreeJobStatus.READY
    assert ready.result is result
    assert ready.completed_at is not None


def test_cannot_mark_ready_from_pending():
    job = _new_job()
    with pytest.raises(InvalidScaffoldTreeJobTransition):
        job.mark_ready(
            ScaffoldTreeResult(),
            datetime(2026, 5, 17, 0, 1, tzinfo=timezone.utc),
        )


def test_running_to_failed():
    job = _new_job().mark_running(datetime(2026, 5, 17, 0, 1, tzinfo=timezone.utc))
    failed = job.mark_failed("boom", datetime(2026, 5, 17, 0, 2, tzinfo=timezone.utc))
    assert failed.status == ScaffoldTreeJobStatus.FAILED
    assert failed.error_message == "boom"


def test_pending_or_running_to_cancelled():
    pending = _new_job()
    c1 = pending.mark_cancelled(datetime(2026, 5, 17, 0, 1, tzinfo=timezone.utc))
    assert c1.status == ScaffoldTreeJobStatus.CANCELLED

    running = _new_job().mark_running(datetime(2026, 5, 17, 0, 1, tzinfo=timezone.utc))
    c2 = running.mark_cancelled(datetime(2026, 5, 17, 0, 2, tzinfo=timezone.utc))
    assert c2.status == ScaffoldTreeJobStatus.CANCELLED


def test_ready_is_terminal():
    job = (
        _new_job()
        .mark_running(datetime(2026, 5, 17, 0, 1, tzinfo=timezone.utc))
        .mark_ready(
            ScaffoldTreeResult(),
            datetime(2026, 5, 17, 0, 2, tzinfo=timezone.utc),
        )
    )
    with pytest.raises(InvalidScaffoldTreeJobTransition):
        job.mark_failed("oops", datetime(2026, 5, 17, 0, 3, tzinfo=timezone.utc))


def test_cancelled_is_terminal():
    cancelled = _new_job().mark_cancelled(datetime(2026, 5, 17, 0, 1, tzinfo=timezone.utc))
    with pytest.raises(InvalidScaffoldTreeJobTransition):
        cancelled.mark_running(datetime(2026, 5, 17, 0, 2, tzinfo=timezone.utc))
