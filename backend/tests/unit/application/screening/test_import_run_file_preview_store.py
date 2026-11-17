"""The run-file preview store holds at most ``max_bytes`` of uploads."""

from __future__ import annotations

import uuid

from cellar.application.screening.import_run_file_preview_store import (
    InMemoryPreviewStore,
    _StoredPreview,
)
from cellar.infrastructure.parsers.tabular_file import parse_tabular


def _stored(size: int) -> _StoredPreview:
    return _StoredPreview(
        workspace_id=uuid.uuid4(),
        run_id=uuid.uuid4(),
        table=parse_tabular(b"Well,Raw\nA1,0.5\n", "x.csv"),
        raw_bytes=b"x" * size,
        filename="x.csv",
        content_type="text/csv",
    )


def test_the_least_recently_used_previews_go_past_the_byte_cap() -> None:
    now = [0.0]
    store = InMemoryPreviewStore(max_bytes=250, clock=lambda: now[0])
    a, b, c = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    store.save(a, _stored(100))
    now[0] = 1
    store.save(b, _stored(100))
    now[0] = 2
    store.peek(a)
    store.save(c, _stored(100))

    assert store.peek(b) is None
    assert store.peek(a) is not None and store.peek(c) is not None


def test_the_newest_preview_stays_even_when_it_alone_passes_the_cap() -> None:
    store = InMemoryPreviewStore(max_bytes=50)
    store.save(old := uuid.uuid4(), _stored(10))
    store.save(new := uuid.uuid4(), _stored(100))
    assert store.peek(old) is None and store.peek(new) is not None
