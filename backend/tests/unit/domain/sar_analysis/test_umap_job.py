"""Tests for the UmapJob state machine."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from cellar.domain.sar_analysis.umap_job import UmapJob
from cellar.domain.sar_analysis.umap_types import UmapResult
from cellar.domain.shared.async_job import AsyncJobStatus, InvalidJobTransition

_NOW = datetime(2026, 5, 18, 12, 0, 0, tzinfo=timezone.utc)
_LATER = datetime(2026, 5, 18, 12, 1, 0, tzinfo=timezone.utc)
_LATEST = datetime(2026, 5, 18, 12, 2, 0, tzinfo=timezone.utc)


def _empty_result() -> UmapResult:
    return UmapResult(
        points=[],
        clusters=[],
        representatives=[],
        cluster_count=0,
        picker="maxmin",
        picker_params={"n": 50},
        skipped_molecule_ids=[],
    )


def _new_job() -> UmapJob:
    return UmapJob.create(
        workspace_id=uuid4(),
        requested_by=uuid4(),
        ids_hash="h",
        picker="maxmin",
        picker_params={"n": 50},
        picker_param_hash="ph",
        now=_NOW,
    )


def test_create_starts_pending() -> None:
    job = _new_job()
    assert job.status == AsyncJobStatus.PENDING
    assert job.started_at is None
    assert job.result is None


def test_running_to_ready() -> None:
    job = _new_job()
    job.mark_running(_LATER)
    result = _empty_result()
    job.mark_ready(result=result, now=_LATEST)
    assert job.status == AsyncJobStatus.READY
    assert job.result is result
    assert job.completed_at == _LATEST


def test_cannot_ready_from_pending() -> None:
    job = _new_job()
    with pytest.raises(InvalidJobTransition):
        job.mark_ready(result=_empty_result(), now=_LATER)
