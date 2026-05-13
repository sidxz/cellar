"""In-memory implementation of the ``ImportFileCache`` protocol.

This is intentionally process-local. A future migration can swap it for a
Valkey/Redis-backed cache without changing application callers — they
depend on the protocol in ``application/shared/import_file_cache.py``.
"""

from __future__ import annotations

import time
import uuid


class InMemoryImportFileCache:
    """In-process cache for uploaded import files between preview/validate/execute.

    Registered as a DI singleton so it survives across requests within the
    same worker process. Entries expire after ``ttl_seconds`` (default 30
    minutes) to prevent memory leaks from abandoned imports.
    """

    def __init__(self, ttl_seconds: int = 1800) -> None:
        self._ttl = ttl_seconds
        # Key is workspace-scoped: "{workspace_id}:{file_id}"
        self._store: dict[str, tuple[float, list[str], list[list[str]]]] = {}

    @staticmethod
    def _key(workspace_id: uuid.UUID, file_id: str) -> str:
        return f"{workspace_id}:{file_id}"

    def _evict_expired(self) -> None:
        now = time.monotonic()
        expired = [k for k, (ts, _, _) in self._store.items() if now - ts > self._ttl]
        for k in expired:
            del self._store[k]

    def put(
        self,
        workspace_id: uuid.UUID,
        file_id: str,
        headers: list[str],
        data_rows: list[list[str]],
    ) -> None:
        self._evict_expired()
        self._store[self._key(workspace_id, file_id)] = (
            time.monotonic(),
            headers,
            data_rows,
        )

    def get(
        self, workspace_id: uuid.UUID, file_id: str
    ) -> tuple[list[str], list[list[str]]] | None:
        self._evict_expired()
        entry = self._store.get(self._key(workspace_id, file_id))
        if entry is None:
            return None
        return (entry[1], entry[2])

    def pop(
        self, workspace_id: uuid.UUID, file_id: str
    ) -> tuple[list[str], list[list[str]]] | None:
        entry = self._store.pop(self._key(workspace_id, file_id), None)
        if entry is None:
            return None
        return (entry[1], entry[2])

    def contains(self, workspace_id: uuid.UUID, file_id: str) -> bool:
        self._evict_expired()
        return self._key(workspace_id, file_id) in self._store
