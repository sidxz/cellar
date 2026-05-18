"""Tests for the UmapJob state machine."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from cellar.domain.sar_analysis.umap_job import (
    InvalidUmapJobTransition,
    UmapJob,
    UmapJobStatus,
)
from cellar.domain.sar_analysis.umap_types import UmapResult


def _now() -> datetime:
    return datetime(2026, 5, 18, 12, 0, 0, tzinfo=timezone.utc)


def _empty_result() -> UmapResult:
    return UmapResult(
        points=[],
        clusters=[],
        representatives=[],
        cluster_count=0,
        picker="maxmin",
        picker_params={"n": 50},
    )


def test_create_starts_pending() -> None:
    job = UmapJob.create(
        workspace_id=uuid4(),
        requested_by=uuid4(),
        ids_hash="h",
        picker="maxmin",
        picker_params={"n": 50},
        picker_param_hash="ph",
        now=_now(),
    )
    assert job.status == UmapJobStatus.PENDING


def test_pending_to_running_to_ready() -> None:
    job = UmapJob.create(
        workspace_id=uuid4(), requested_by=uuid4(), ids_hash="h",
        picker="maxmin", picker_params={"n": 50}, picker_param_hash="ph",
        now=_now(),
    )
    job = job.mark_running(_now())
    assert job.status == UmapJobStatus.RUNNING
    job = job.mark_ready(_empty_result(), _now())
    assert job.status == UmapJobStatus.READY
    assert job.result is not None


def test_cannot_ready_from_pending() -> None:
    job = UmapJob.create(
        workspace_id=uuid4(), requested_by=uuid4(), ids_hash="h",
        picker="maxmin", picker_params={"n": 50}, picker_param_hash="ph",
        now=_now(),
    )
    with pytest.raises(InvalidUmapJobTransition):
        job.mark_ready(_empty_result(), _now())


def test_cannot_cancel_terminal() -> None:
    job = (
        UmapJob.create(
            workspace_id=uuid4(), requested_by=uuid4(), ids_hash="h",
            picker="maxmin", picker_params={"n": 50}, picker_param_hash="ph",
            now=_now(),
        )
        .mark_running(_now())
        .mark_failed("oops", _now())
    )
    with pytest.raises(InvalidUmapJobTransition):
        job.mark_cancelled(_now())
