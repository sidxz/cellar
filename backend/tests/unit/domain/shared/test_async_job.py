from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from cellar.domain.shared.async_job import (
    JOB_TERMINAL_STATES,
    AsyncJob,
    AsyncJobStatus,
    InvalidJobTransition,
)

_NOW = datetime(2026, 6, 16, tzinfo=UTC)


class _FakeJob(AsyncJob):
    """Minimal concrete AsyncJob for exercising the shared base."""

    def __init__(self, *, result: str | None = None, **kwargs) -> None:
        super().__init__(**kwargs)
        self.result = result

    def mark_ready(self, *, result: str, now: datetime) -> None:
        self._enter_ready(now)
        self.result = result


def _pending() -> _FakeJob:
    return _FakeJob(
        workspace_id=uuid.uuid4(),
        requested_by=uuid.uuid4(),
        requested_at=_NOW,
    )


def test_new_job_is_pending_with_version_1():
    job = _pending()
    assert job.status == AsyncJobStatus.PENDING
    assert job.version == 1
    assert job.started_at is None and job.completed_at is None


def test_mark_running_from_pending():
    job = _pending()
    job.mark_running(_NOW)
    assert job.status == AsyncJobStatus.RUNNING
    assert job.started_at == _NOW


def test_mark_running_twice_raises():
    job = _pending()
    job.mark_running(_NOW)
    with pytest.raises(InvalidJobTransition):
        job.mark_running(_NOW)


def test_mark_ready_from_running_sets_result():
    job = _pending()
    job.mark_running(_NOW)
    job.mark_ready(result="done", now=_NOW)
    assert job.status == AsyncJobStatus.READY
    assert job.completed_at == _NOW
    assert job.result == "done"
    assert job.started_at == _NOW


def test_mark_ready_from_pending_raises():
    job = _pending()
    with pytest.raises(InvalidJobTransition):
        job.mark_ready(result="x", now=_NOW)


def test_mark_failed_from_running():
    job = _pending()
    job.mark_running(_NOW)
    job.mark_failed("boom", _NOW)
    assert job.status == AsyncJobStatus.FAILED
    assert job.error_message == "boom"
    assert job.completed_at == _NOW


def test_mark_failed_from_pending():
    job = _pending()
    job.mark_failed("boom", _NOW)
    assert job.status == AsyncJobStatus.FAILED


def test_mark_failed_from_terminal_raises():
    job = _pending()
    job.mark_cancelled(_NOW)
    with pytest.raises(InvalidJobTransition):
        job.mark_failed("boom", _NOW)


def test_mark_failed_from_ready_raises():
    job = _pending()
    job.mark_running(_NOW)
    job.mark_ready(result="done", now=_NOW)
    with pytest.raises(InvalidJobTransition):
        job.mark_failed("boom", _NOW)


def test_mark_cancelled_from_pending():
    job = _pending()
    job.mark_cancelled(_NOW)
    assert job.status == AsyncJobStatus.CANCELLED
    assert job.completed_at == _NOW


def test_mark_cancelled_from_running():
    job = _pending()
    job.mark_running(_NOW)
    job.mark_cancelled(_NOW)
    assert job.status == AsyncJobStatus.CANCELLED


def test_mark_cancelled_from_terminal_raises():
    job = _pending()
    job.mark_cancelled(_NOW)
    with pytest.raises(InvalidJobTransition):
        job.mark_cancelled(_NOW)


def test_transitions_do_not_bump_version():
    # version is owned by the repository's optimistic-concurrency save(), never
    # by a domain transition.
    job = _pending()
    job.mark_running(_NOW)
    job.mark_ready(result="done", now=_NOW)
    assert job.version == 1


def test_terminal_states_are_non_pending_non_running():
    assert frozenset(AsyncJobStatus) - {
        AsyncJobStatus.PENDING,
        AsyncJobStatus.RUNNING,
    } == JOB_TERMINAL_STATES
