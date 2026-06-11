from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

from cellar.domain.sar_analysis.rgroup_decomposition_run import (
    InvalidRGroupRunTransition,
    RGroupDecompositionRun,
    RGroupDecompositionRunStatus,
)

_NOW = datetime(2026, 6, 11, tzinfo=timezone.utc)


def _new_run() -> RGroupDecompositionRun:
    return RGroupDecompositionRun.create(
        workspace_id=uuid.uuid4(),
        requested_by=uuid.uuid4(),
        membership_hash="m-hash",
        core_smiles="c1ccccc1",
        core_hash="c-hash",
        now=_NOW,
    )


def test_create_starts_pending_with_zero_counts():
    run = _new_run()
    assert run.status == RGroupDecompositionRunStatus.PENDING
    assert run.rgroup_labels == []
    assert run.matched_count == 0
    assert run.total_count == 0


def test_mark_ready_records_labels_and_counts():
    run = _new_run().mark_running(_NOW)
    ready = run.mark_ready(
        rgroup_labels=["R1", "R2"],
        matched_count=8,
        unmatched_count=2,
        total_count=10,
        now=_NOW,
    )
    assert ready.status == RGroupDecompositionRunStatus.READY
    assert ready.rgroup_labels == ["R1", "R2"]
    assert ready.matched_count == 8
    assert ready.unmatched_count == 2
    assert ready.total_count == 10
    assert ready.completed_at == _NOW


def test_cannot_mark_ready_from_pending():
    with pytest.raises(InvalidRGroupRunTransition):
        _new_run().mark_ready(
            rgroup_labels=[], matched_count=0, unmatched_count=0, total_count=0, now=_NOW
        )


def test_mark_failed_from_running_records_error():
    failed = _new_run().mark_running(_NOW).mark_failed("boom", _NOW)
    assert failed.status == RGroupDecompositionRunStatus.FAILED
    assert failed.error_message == "boom"


def test_ready_is_terminal():
    ready = _new_run().mark_running(_NOW).mark_ready(
        rgroup_labels=[], matched_count=0, unmatched_count=0, total_count=0, now=_NOW
    )
    with pytest.raises(InvalidRGroupRunTransition):
        ready.mark_cancelled(_NOW)


def test_cancel_from_pending_succeeds():
    cancelled = _new_run().mark_cancelled(_NOW)
    assert cancelled.status == RGroupDecompositionRunStatus.CANCELLED


def test_cancel_from_running_succeeds():
    cancelled = _new_run().mark_running(_NOW).mark_cancelled(_NOW)
    assert cancelled.status == RGroupDecompositionRunStatus.CANCELLED


def test_cancelled_is_terminal():
    # Guards _TERMINAL: a cancelled run cannot be re-run. mark_running only checks
    # `!= PENDING`, so without CANCELLED in _TERMINAL this would wrongly succeed.
    cancelled = _new_run().mark_cancelled(_NOW)
    with pytest.raises(InvalidRGroupRunTransition):
        cancelled.mark_running(_NOW)
