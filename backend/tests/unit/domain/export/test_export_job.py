from __future__ import annotations
import uuid
from datetime import datetime, timedelta, UTC

import pytest

from cellar.domain.export.enums import ExportFormat, ExportSource, ExportStatus
from cellar.domain.export.export_job import ExportJob
from cellar.domain.shared.errors import ConflictError


def _make(**overrides) -> ExportJob:
    base = dict(
        id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        requested_by=uuid.uuid4(),
        source=ExportSource.SEARCH,
        format=ExportFormat.CSV,
        query_snapshot={"query": {}, "protocol_columns": []},
        filename="cellar-search.csv",
    )
    base.update(overrides)
    return ExportJob.create(**base)


def test_create_starts_pending():
    job = _make()
    assert job.status == ExportStatus.PENDING
    assert job.progress is None
    assert job.row_count is None
    assert job.requested_at is not None
    assert job.expires_at is None


def test_mark_running_from_pending():
    job = _make()
    job.mark_running()
    assert job.status == ExportStatus.RUNNING
    assert job.started_at is not None


def test_mark_running_from_other_raises():
    job = _make()
    job.mark_running()
    with pytest.raises(ConflictError):
        job.mark_running()


def test_set_row_count():
    job = _make()
    job.mark_running()
    job.set_row_count(1234)
    assert job.row_count == 1234


def test_report_progress_clamped():
    job = _make()
    job.mark_running()
    job.set_row_count(100)
    job.report_progress(0.5)
    assert job.progress == 0.5
    job.report_progress(1.5)  # clamp
    assert job.progress == 1.0
    job.report_progress(-0.1)
    assert job.progress == 0.0


def test_mark_ready_sets_download_metadata():
    job = _make()
    job.mark_running()
    expires = datetime.now(UTC) + timedelta(days=7)
    job.mark_ready(
        file_key="exports/ws/x.csv",
        byte_size=1024,
        content_type="text/csv",
        expires_at=expires,
    )
    assert job.status == ExportStatus.READY
    assert job.file_key == "exports/ws/x.csv"
    assert job.byte_size == 1024
    assert job.expires_at == expires
    assert job.completed_at is not None
    assert job.progress == 1.0


def test_mark_failed_records_error():
    job = _make()
    job.mark_running()
    job.mark_failed("disk full")
    assert job.status == ExportStatus.FAILED
    assert job.error_message == "disk full"
    assert job.completed_at is not None


def test_cancel_flow():
    job = _make()
    job.mark_running()
    job.request_cancel()
    assert job.status == ExportStatus.CANCEL_REQUESTED
    job.mark_cancelled()
    assert job.status == ExportStatus.CANCELLED


def test_cannot_cancel_terminal_job():
    job = _make()
    job.mark_running()
    job.mark_failed("x")
    with pytest.raises(ConflictError):
        job.request_cancel()


def test_mark_expired_requires_ready():
    job = _make()
    job.mark_running()
    with pytest.raises(ConflictError):
        job.mark_expired()
    job.mark_ready("k", 1, "text/csv", datetime.now(UTC))
    job.mark_expired()
    assert job.status == ExportStatus.EXPIRED
    assert job.file_key is None  # storage swept
