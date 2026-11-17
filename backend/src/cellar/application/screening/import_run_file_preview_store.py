"""Preview store for the run-file import wizard.

Extracted from ``import_run_file.py`` to keep that module focused on the
use case orchestration. The store caches the parsed ``ParsedTable`` plus
the raw uploaded bytes between the preview and import calls so the
wizard can render the preview, let the chemist refine the column
mapping, and then commit — without re-uploading the file.

Raw bytes are kept so the importer can persist the original upload as a
Run attachment after a successful write — the Files tab is the
canonical audit log of what was uploaded for the run.

A preview lives 30 minutes from its last use; the wizard re-uploads the
file it holds when the server no longer has it (restart, eviction).
"""

from __future__ import annotations

import time
import uuid
from collections import OrderedDict
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from cellar.application.shared.parsers import ParsedTable

# The largest run file the wizard takes: 50,000 rows (the parser's limit) of a wide export.
MAX_RUN_FILE_BYTES = 50 * 1024 * 1024


@dataclass(frozen=True)
class _StoredPreview:
    """Cached parsed file + raw bytes bound to a preview_id.

    Raw bytes are kept so the importer can persist the original upload
    as a Run attachment after a successful write — the Files tab is
    the canonical audit log of what was uploaded for the run.
    """

    workspace_id: uuid.UUID
    run_id: uuid.UUID
    table: ParsedTable
    raw_bytes: bytes
    filename: str
    content_type: str


@runtime_checkable
class PreviewStore(Protocol):
    """Short-lived store for parsed preview tables."""

    @property
    def ttl_seconds(self) -> float: ...
    def save(self, key: uuid.UUID, payload: _StoredPreview) -> None: ...
    def consume(self, key: uuid.UUID) -> _StoredPreview | None: ...
    def peek(self, key: uuid.UUID) -> _StoredPreview | None: ...


class InMemoryPreviewStore:
    """In-process preview store. A preview lives ``ttl_seconds`` from its last
    save or peek; past ``max_items`` previews or ``max_bytes`` of uploads the
    least recently used go first (the newest always stays).

    ponytail: one process only (prod runs one uvicorn worker). More workers
    need a shared store (Valkey); ``max_bytes`` counts the uploads, not the
    parsed tables they become.
    """

    def __init__(
        self,
        ttl_seconds: float = 30 * 60,
        *,
        max_items: int = 50,
        max_bytes: int = 500 * 1024 * 1024,
        clock=time.monotonic,
    ) -> None:
        # Ordered by last use, oldest first: the expired and the evicted are at the front.
        self._items: OrderedDict[uuid.UUID, tuple[_StoredPreview, float]] = OrderedDict()
        self._ttl = ttl_seconds
        self._max_items = max_items
        self._max_bytes = max_bytes
        self._clock = clock

    @property
    def ttl_seconds(self) -> float:
        return self._ttl

    def save(self, key: uuid.UUID, payload: _StoredPreview) -> None:
        self._touch(key, payload)
        while len(self._items) > 1 and (
            len(self._items) > self._max_items
            or sum(len(p.raw_bytes) for p, _ in self._items.values()) > self._max_bytes
        ):
            self._items.popitem(last=False)

    def consume(self, key: uuid.UUID) -> _StoredPreview | None:
        self._evict_expired()
        item = self._items.pop(key, None)
        return item[0] if item else None

    def peek(self, key: uuid.UUID) -> _StoredPreview | None:
        """Return the cached payload without removing it, restarting its clock.

        Used by ``RepreviewRunFile`` so the chemist can refine the column
        mapping in the wizard's mapping step and re-run resolution
        without re-uploading the file.
        """
        self._evict_expired()
        item = self._items.get(key)
        if item is None:
            return None
        self._touch(key, item[0])
        return item[0]

    def _touch(self, key: uuid.UUID, payload: _StoredPreview) -> None:
        self._evict_expired()
        self._items[key] = (payload, self._clock())
        self._items.move_to_end(key)

    def _evict_expired(self) -> None:
        cutoff = self._clock() - self._ttl
        while self._items and next(iter(self._items.values()))[1] <= cutoff:
            self._items.popitem(last=False)


_CONTENT_TYPE_BY_EXT: dict[str, str] = {
    ".csv": "text/csv",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".xls": "application/vnd.ms-excel",
    ".tsv": "text/tab-separated-values",
}


def _guess_content_type(filename: str) -> str:
    if not filename:
        return "application/octet-stream"
    lower = filename.lower()
    for ext, ct in _CONTENT_TYPE_BY_EXT.items():
        if lower.endswith(ext):
            return ct
    return "application/octet-stream"
