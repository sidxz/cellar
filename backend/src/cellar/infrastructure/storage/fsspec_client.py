"""File storage: the one root every on-disk write hangs off, plus the fsspec client.

``STORAGE_ROOT`` is the single env var for files. In prod it is a mounted volume
(``/data/storage``); everything the app persists — attachments, export downloads,
bulk-import uploads, CDD export dumps — lives in a subdirectory of it. Anything
written elsewhere inside a container dies with the container, so
``ensure_storage_root`` refuses to boot a production process whose root is not on
a mounted volume.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Callable
from functools import partial
from pathlib import Path, PurePosixPath

import fsspec
import structlog
from pydantic import Field
from pydantic_settings import BaseSettings

# Re-export for backward compatibility with existing test imports.
from cellar.domain.attachment.validation import (  # noqa: F401
    BLOCKED_EXTENSIONS,
    MAX_FILE_SIZE,
    validate_extension,
    validate_file_size,
)

logger = structlog.get_logger(__name__)


class StorageSettings(BaseSettings):
    """Where the app keeps files. Env: ``STORAGE_ROOT``; default is host-dev relative."""

    storage_root: str = Field(default="./data/storage")

    @property
    def root_path(self) -> Path:
        return Path(self.storage_root)

    def subdir(self, name: str) -> Path:
        return self.root_path / name


def _on_mounted_volume(path: Path, is_mount: Callable[[str], bool]) -> bool:
    """True if ``path`` or an ancestor is a mount point other than the filesystem root."""
    for candidate in (path, *path.parents):
        if candidate == Path(candidate.anchor):
            return False
        if is_mount(str(candidate)):
            return True
    return False


def ensure_storage_root(
    settings: StorageSettings,
    *,
    production: bool | None = None,
    is_mount: Callable[[str], bool] = os.path.ismount,
) -> Path:
    """Create the storage root and prove it is usable, or abort the process.

    Called at API and worker startup. A production root that is not on a mounted
    volume would silently store files inside the container, so that is a boot
    failure rather than a warning.
    """
    root = settings.root_path.resolve()
    if production is None:
        production = os.environ.get("APP_ENV") == "production"
    if production and not _on_mounted_volume(root, is_mount):
        raise RuntimeError(
            f"STORAGE_ROOT={root} is not on a mounted volume; files written there "
            "would die with the container. Mount a volume there or fix STORAGE_ROOT."
        )
    try:
        root.mkdir(parents=True, exist_ok=True)
        # Per-process name: API and worker boot together on the same volume.
        probe = root / f".write-probe-{os.getpid()}"
        probe.write_bytes(b"")
        probe.unlink(missing_ok=True)
    except OSError as exc:
        raise RuntimeError(f"STORAGE_ROOT={root} is not writable: {exc}") from exc
    logger.info("storage.root_ready", root=str(root), production=production)
    return root


class FsspecStorageClient:
    """Local-filesystem storage client using fsspec.

    Storage key format: {workspace_id}/{attachable_type}/{attachable_id}/{uuid}_{filename}
    Full path: {STORAGE_ROOT}/attachments/{key}
    """

    def __init__(self, settings: StorageSettings | None = None) -> None:
        self._base = str((settings or StorageSettings()).subdir("attachments"))
        self._fs = fsspec.filesystem("file")

    def _full_path(self, key: str) -> str:
        return f"{self._base}/{key}"

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
            logger.warning("storage.key_not_found_on_delete", storage_key=key)
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
        await asyncio.get_running_loop().run_in_executor(None, partial(self._sync_delete, key))
