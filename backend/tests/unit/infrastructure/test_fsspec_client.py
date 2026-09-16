"""Unit tests for FsspecStorageClient, StorageSettings and the startup guard."""

import os
from pathlib import Path

import pytest

from cellar.domain.shared.errors import ValidationError
from cellar.infrastructure.storage.fsspec_client import (
    MAX_FILE_SIZE,
    FsspecStorageClient,
    StorageSettings,
    ensure_storage_root,
    validate_extension,
    validate_file_size,
)


class TestValidateExtension:
    def test_allowed_extension(self):
        validate_extension("report.pdf")

    def test_blocked_exe(self):
        with pytest.raises(ValidationError, match="blocked"):
            validate_extension("malware.exe")

    def test_blocked_sh(self):
        with pytest.raises(ValidationError, match="blocked"):
            validate_extension("script.sh")

    def test_blocked_zip(self):
        with pytest.raises(ValidationError, match="blocked"):
            validate_extension("archive.zip")

    def test_no_extension_allowed(self):
        validate_extension("README")

    def test_case_insensitive(self):
        with pytest.raises(ValidationError, match="blocked"):
            validate_extension("virus.EXE")


class TestValidateFileSize:
    def test_under_limit(self):
        validate_file_size(1024 * 1024)  # 1 MB — should not raise

    def test_at_limit(self):
        validate_file_size(MAX_FILE_SIZE)  # exactly 100 MB — should not raise

    def test_over_limit(self):
        with pytest.raises(ValidationError, match="exceeds maximum"):
            validate_file_size(MAX_FILE_SIZE + 1)


class TestFsspecStorageClient:
    @pytest.fixture
    def client(self, tmp_path):
        settings = StorageSettings(storage_root=str(tmp_path))
        return FsspecStorageClient(settings)

    async def test_files_land_under_the_attachments_subdir_of_storage_root(self, client, tmp_path):
        """The one invariant that matters in prod: everything under STORAGE_ROOT."""
        key = "ws1/run/run1/abc_data.csv"
        await client.upload(key, b"x")
        assert (tmp_path / "attachments" / "ws1/run/run1/abc_data.csv").read_bytes() == b"x"

    async def test_upload_and_download(self, client, tmp_path):
        data = b"hello world"
        key = "ws1/molecule/mol1/abc_test.txt"
        await client.upload(key, data)
        result = await client.download(key)
        assert result == data

    async def test_delete(self, client, tmp_path):
        key = "ws1/molecule/mol1/abc_test.txt"
        await client.upload(key, b"data")
        await client.delete(key)
        with pytest.raises(FileNotFoundError):
            await client.download(key)

    async def test_download_missing_key(self, client):
        with pytest.raises(FileNotFoundError):
            await client.download("nonexistent/key")

    async def test_delete_missing_key_is_noop(self, client):
        await client.delete("nonexistent/key")


class TestStorageSettings:
    def test_reads_storage_root_env(self, monkeypatch):
        monkeypatch.setenv("STORAGE_ROOT", "/data/storage")
        assert StorageSettings().storage_root == "/data/storage"

    def test_default_is_host_dev_relative(self, monkeypatch):
        monkeypatch.delenv("STORAGE_ROOT", raising=False)
        assert StorageSettings().storage_root == "./data/storage"

    def test_subdirs_hang_off_the_root(self):
        s = StorageSettings(storage_root="/data/storage")
        assert s.subdir("attachments") == Path("/data/storage/attachments")
        assert s.subdir("bulk-imports") == Path("/data/storage/bulk-imports")


class TestEnsureStorageRoot:
    def test_creates_root_and_proves_it_writable(self, tmp_path):
        root = tmp_path / "storage"
        out = ensure_storage_root(StorageSettings(storage_root=str(root)), production=False)
        assert out == root.resolve()
        assert root.is_dir()
        assert list(root.iterdir()) == []  # probe file cleaned up

    @pytest.mark.skipif(os.geteuid() == 0, reason="root ignores directory permissions")
    def test_unwritable_root_aborts(self, tmp_path):
        ro = tmp_path / "ro"
        ro.mkdir()
        ro.chmod(0o500)
        try:
            with pytest.raises(RuntimeError, match="not writable"):
                ensure_storage_root(
                    StorageSettings(storage_root=str(ro / "storage")), production=False
                )
        finally:
            ro.chmod(0o700)

    def test_production_requires_a_mounted_volume(self, tmp_path):
        """In production a root on the container's own filesystem must refuse to boot."""
        with pytest.raises(RuntimeError, match="mounted volume"):
            ensure_storage_root(
                StorageSettings(storage_root=str(tmp_path)),
                production=True,
                is_mount=lambda p: False,
            )

    def test_production_accepts_root_on_or_under_a_mount(self, tmp_path):
        root = tmp_path / "storage"
        mounted = {str(tmp_path.resolve())}
        out = ensure_storage_root(
            StorageSettings(storage_root=str(root)),
            production=True,
            is_mount=lambda p: str(p) in mounted,
        )
        assert out == root.resolve()

    def test_production_flag_defaults_from_app_env(self, tmp_path, monkeypatch):
        monkeypatch.setenv("APP_ENV", "production")
        with pytest.raises(RuntimeError, match="mounted volume"):
            ensure_storage_root(
                StorageSettings(storage_root=str(tmp_path)), is_mount=lambda p: False
            )
