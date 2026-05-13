"""Unit tests for FsspecStorageClient."""

import pytest

from cellar.infrastructure.storage.fsspec_client import (
    BLOCKED_EXTENSIONS,
    FsspecStorageClient,
    MAX_FILE_SIZE,
    StorageSettings,
    validate_extension,
    validate_file_size,
)
from cellar.domain.shared.errors import ValidationError


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
        settings = StorageSettings(base_path=str(tmp_path))
        return FsspecStorageClient(settings)

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
