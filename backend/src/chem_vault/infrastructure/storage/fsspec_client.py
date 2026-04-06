"""Fsspec-backed storage client for file attachments."""

from __future__ import annotations

import logging
from pathlib import PurePosixPath

import fsspec
from pydantic import Field
from pydantic_settings import BaseSettings

from chem_vault.domain.shared.errors import ValidationError

logger = logging.getLogger(__name__)

BLOCKED_EXTENSIONS: set[str] = {
    ".exe", ".sh", ".bat", ".cmd", ".ps1", ".dll", ".so",
    ".com", ".msi", ".scr", ".zip", ".tar", ".gz", ".7z",
    ".rar", ".war", ".jar",
}

MAX_FILE_SIZE: int = 104_857_600  # 100 MB


def validate_extension(file_name: str) -> None:
    """Raise ValidationError if the file extension is blocked."""
    suffix = PurePosixPath(file_name).suffix.lower()
    if suffix in BLOCKED_EXTENSIONS:
        raise ValidationError(f"File extension '{suffix}' is blocked")


def validate_file_size(size: int) -> None:
    """Raise ValidationError if file exceeds the size limit."""
    if size > MAX_FILE_SIZE:
        raise ValidationError(
            f"File size {size} bytes exceeds maximum {MAX_FILE_SIZE} bytes (100 MB)"
        )


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

    async def upload(self, key: str, data: bytes) -> None:
        """Write data to storage."""
        path = self._full_path(key)
        parent = str(PurePosixPath(path).parent)
        self._fs.mkdirs(parent, exist_ok=True)
        with self._fs.open(path, "wb") as f:
            f.write(data)

    async def download(self, key: str) -> bytes:
        """Read data from storage. Raises FileNotFoundError if missing."""
        path = self._full_path(key)
        if not self._fs.exists(path):
            raise FileNotFoundError(f"Storage key not found: {key}")
        with self._fs.open(path, "rb") as f:
            return f.read()

    async def delete(self, key: str) -> None:
        """Delete from storage. Best-effort — logs warning if missing."""
        path = self._full_path(key)
        if not self._fs.exists(path):
            logger.warning("Storage key not found during delete: %s", key)
            return
        self._fs.rm(path)
