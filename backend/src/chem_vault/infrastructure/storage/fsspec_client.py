"""Fsspec-backed storage client for file attachments."""

from __future__ import annotations

import asyncio
from functools import partial
from pathlib import PurePosixPath

import fsspec
import structlog
from pydantic import Field
from pydantic_settings import BaseSettings

# Re-export for backward compatibility with existing test imports.
from chem_vault.domain.attachment.validation import (  # noqa: F401
    BLOCKED_EXTENSIONS,
    MAX_FILE_SIZE,
    validate_extension,
    validate_file_size,
)

logger = structlog.get_logger(__name__)


class StorageSettings(BaseSettings):
    """Configuration for blob storage."""

    base_path: str = Field(default="./data/attachments")


class FsspecStorageClient:
    """Local-filesystem storage client using fsspec.

    Storage key format: {workspace_id}/{attachable_type}/{attachable_id}/{uuid}_{filename}
    Full path: {base_path}/{key}
    """

    def __init__(self, settings: StorageSettings | None = None) -> None:
        self._settings = settings or StorageSettings()
        self._fs = fsspec.filesystem("file")

    def _full_path(self, key: str) -> str:
        return f"{self._settings.base_path}/{key}"

    def _sync_upload(self, key: str, data: bytes) -> None:
        path = self._full_path(key)
        parent = str(PurePosixPath(path).parent)
        self._fs.mkdirs(parent, exist_ok=True)
        with self._fs.open(path, "wb") as f:
            f.write(data)

    def _sync_download(self, key: str) -> bytes:
        path = self._full_path(key)
        if not self._fs.exists(path):
            raise FileNotFoundError(f"Storage key not found: {key}")
        with self._fs.open(path, "rb") as f:
            return f.read()

    def _sync_delete(self, key: str) -> None:
        path = self._full_path(key)
        if not self._fs.exists(path):
            logger.warning("Storage key not found during delete: %s", key)
            return
        self._fs.rm(path)

    async def upload(self, key: str, data: bytes) -> None:
        """Write data to storage (runs blocking I/O in a thread)."""
        await asyncio.get_running_loop().run_in_executor(
            None, partial(self._sync_upload, key, data)
        )

    async def download(self, key: str) -> bytes:
        """Read data from storage (runs blocking I/O in a thread)."""
        return await asyncio.get_running_loop().run_in_executor(
            None, partial(self._sync_download, key)
        )

    async def delete(self, key: str) -> None:
        """Delete from storage (runs blocking I/O in a thread)."""
        await asyncio.get_running_loop().run_in_executor(
            None, partial(self._sync_delete, key)
        )
