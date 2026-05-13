"""Short-lived in-memory preview store for the run-file import wizard.

Extracted from ``import_run_file.py`` to keep that module focused on the
use case orchestration. The store caches the parsed ``ParsedTable`` plus
the raw uploaded bytes between the preview and import calls so the
wizard can render the preview, let the chemist refine the column
mapping, and then commit — without re-uploading the file.

Raw bytes are kept so the importer can persist the original upload as a
Run attachment after a successful write — the Files tab is the
canonical audit log of what was uploaded for the run.

Single-process only: the in-memory implementation evicts on TTL or on
first consume. Swap in a Redis-backed store if/when this needs to span
workers.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from cellar.application.shared.parsers import ParsedTable


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
    expires_at: float


@runtime_checkable
class PreviewStore(Protocol):
    """Short-lived store for parsed preview tables."""

    def save(self, key: uuid.UUID, payload: _StoredPreview) -> None: ...
    def consume(self, key: uuid.UUID) -> _StoredPreview | None: ...
    def peek(self, key: uuid.UUID) -> _StoredPreview | None: ...


class InMemoryPreviewStore:
    """In-process preview store with TTL eviction. Single-process only."""

    def __init__(self, ttl_seconds: float = 60.0, *, clock=time.monotonic) -> None:
        self._items: dict[uuid.UUID, _StoredPreview] = {}
        self._ttl = ttl_seconds
        self._clock = clock

    @property
    def ttl_seconds(self) -> float:
        return self._ttl

    def save(self, key: uuid.UUID, payload: _StoredPreview) -> None:
        self._items[key] = payload

    def consume(self, key: uuid.UUID) -> _StoredPreview | None:
        self._evict_expired()
        return self._items.pop(key, None)

    def peek(self, key: uuid.UUID) -> _StoredPreview | None:
        """Return the cached payload without removing it.

        Used by ``RepreviewRunFile`` so the chemist can refine the column
        mapping in the wizard's mapping step and re-run resolution
        without re-uploading the file.
        """
        self._evict_expired()
        return self._items.get(key)

    def _evict_expired(self) -> None:
        now = self._clock()
        stale = [k for k, v in self._items.items() if v.expires_at <= now]
        for k in stale:
            del self._items[k]


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
