"""Storage client protocol — application-layer abstraction over blob storage."""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class StorageClient(Protocol):
    """Upload, download, and delete file blobs."""

    async def upload(self, key: str, data: bytes) -> None: ...
    async def download(self, key: str) -> bytes: ...
    async def delete(self, key: str) -> None: ...
