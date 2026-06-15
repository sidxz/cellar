from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from cellar.domain.sar_analysis.sar_activity_projection import (
    InvalidSarProjectionTransition,
    SarActivityProjection,
    SarActivityProjectionStatus,
)

_NOW = datetime(2026, 6, 15, tzinfo=UTC)


def _pending() -> SarActivityProjection:
    return SarActivityProjection.create(
        workspace_id=uuid.uuid4(),
        requested_by=uuid.uuid4(),
        membership_hash="m",
        channel_hash="ch",
        channel_spec={"column": "drc:x"},
        now=_NOW,
    )


def test_create_is_pending():
    p = _pending()
    assert p.status == SarActivityProjectionStatus.PENDING
    assert p.value_count == 0
    assert p.channel_spec == {"column": "drc:x"}
    assert p.version == 1


def test_running_then_ready_sets_value_count():
    ready = _pending().mark_running(_NOW).mark_ready(value_count=7, now=_NOW)
    assert ready.status == SarActivityProjectionStatus.READY
    assert ready.value_count == 7
    assert ready.completed_at == _NOW


def test_ready_requires_running():
    with pytest.raises(InvalidSarProjectionTransition):
        _pending().mark_ready(value_count=1, now=_NOW)


def test_failed_from_running_carries_message():
    failed = _pending().mark_running(_NOW).mark_failed("boom", _NOW)
    assert failed.status == SarActivityProjectionStatus.FAILED
    assert failed.error_message == "boom"


def test_cancel_terminal_is_rejected():
    ready = _pending().mark_running(_NOW).mark_ready(value_count=0, now=_NOW)
    with pytest.raises(InvalidSarProjectionTransition):
        ready.mark_cancelled(_NOW)


def test_cancel_pending_ok():
    cancelled = _pending().mark_cancelled(_NOW)
    assert cancelled.status == SarActivityProjectionStatus.CANCELLED
