from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from cellar.domain.sar_analysis.rgroup_decomposition_run import RGroupDecompositionRun
from cellar.domain.shared.async_job import AsyncJobStatus, InvalidJobTransition

_NOW = datetime(2026, 6, 11, tzinfo=UTC)


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
    assert run.status == AsyncJobStatus.PENDING
    assert run.rgroup_labels == []
    assert run.matched_count == 0
    assert run.total_count == 0


def test_mark_ready_records_labels_and_counts():
    run = _new_run()
    run.mark_running(_NOW)
    run.mark_ready(
        rgroup_labels=["R1", "R2"],
        matched_count=8,
        unmatched_count=2,
        total_count=10,
        now=_NOW,
    )
    assert run.status == AsyncJobStatus.READY
    assert run.rgroup_labels == ["R1", "R2"]
    assert run.matched_count == 8
    assert run.unmatched_count == 2
    assert run.total_count == 10
    assert run.completed_at == _NOW


def test_cannot_mark_ready_from_pending():
    run = _new_run()
    with pytest.raises(InvalidJobTransition):
        run.mark_ready(
            rgroup_labels=[], matched_count=0, unmatched_count=0, total_count=0, now=_NOW
        )


def test_mark_failed_from_running_records_error():
    run = _new_run()
    run.mark_running(_NOW)
    run.mark_failed("boom", _NOW)
    assert run.status == AsyncJobStatus.FAILED
    assert run.error_message == "boom"


def test_ready_is_terminal():
    run = _new_run()
    run.mark_running(_NOW)
    run.mark_ready(
        rgroup_labels=[], matched_count=0, unmatched_count=0, total_count=0, now=_NOW
    )
    with pytest.raises(InvalidJobTransition):
        run.mark_cancelled(_NOW)


def test_cancel_from_pending_succeeds():
    run = _new_run()
    run.mark_cancelled(_NOW)
    assert run.status == AsyncJobStatus.CANCELLED


def test_cancel_from_running_succeeds():
    run = _new_run()
    run.mark_running(_NOW)
    run.mark_cancelled(_NOW)
    assert run.status == AsyncJobStatus.CANCELLED


def test_cancelled_is_terminal():
    # mark_running only checks `!= PENDING`, so without CANCELLED in the terminal
    # set this would wrongly succeed.
    run = _new_run()
    run.mark_cancelled(_NOW)
    with pytest.raises(InvalidJobTransition):
        run.mark_running(_NOW)
