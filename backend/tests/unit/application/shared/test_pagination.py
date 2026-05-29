"""Unit tests for pagination cursor helpers."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from cellar.application.shared.pagination import (
    encode_ts_cursor,
    parse_ts_cursor,
)


def test_ts_cursor_round_trips():
    ts = datetime(2026, 5, 29, 18, 30, 15, 123456, tzinfo=timezone.utc)
    id_ = uuid.uuid4()
    cursor = encode_ts_cursor(ts, id_)
    parsed = parse_ts_cursor(cursor)
    assert parsed == (ts, id_)


def test_parse_ts_cursor_none_and_empty():
    assert parse_ts_cursor(None) is None
    assert parse_ts_cursor("") is None


def test_parse_ts_cursor_malformed_degrades_to_none():
    # A garbage cursor must degrade to "first page", never raise.
    assert parse_ts_cursor("not-a-cursor") is None
    assert parse_ts_cursor("2026-05-29T00:00:00|not-a-uuid") is None
    assert parse_ts_cursor("not-a-date|" + str(uuid.uuid4())) is None
