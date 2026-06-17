from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from cellar.domain.sar_analysis.sar_activity_projection import SarActivityProjection
from cellar.domain.shared.async_job import AsyncJobStatus, InvalidJobTransition

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
    assert p.status == AsyncJobStatus.PENDING
    assert p.value_count == 0
    assert p.channel_spec == {"column": "drc:x"}
    assert p.version == 1


def test_running_then_ready_sets_value_count():
    p = _pending()
    p.mark_running(_NOW)
    p.mark_ready(value_count=7, now=_NOW)
    assert p.status == AsyncJobStatus.READY
    assert p.value_count == 7
    assert p.completed_at == _NOW


def test_ready_requires_running():
    with pytest.raises(InvalidJobTransition):
        _pending().mark_ready(value_count=1, now=_NOW)


def test_failed_from_running_carries_message():
    p = _pending()
    p.mark_running(_NOW)
    p.mark_failed("boom", _NOW)
    assert p.status == AsyncJobStatus.FAILED
    assert p.error_message == "boom"


def test_cancel_terminal_is_rejected():
    p = _pending()
    p.mark_running(_NOW)
    p.mark_ready(value_count=0, now=_NOW)
    with pytest.raises(InvalidJobTransition):
        p.mark_cancelled(_NOW)


def test_cancel_pending_ok():
    p = _pending()
    p.mark_cancelled(_NOW)
    assert p.status == AsyncJobStatus.CANCELLED
