"""Pure domain validation for file attachments."""

from __future__ import annotations

from pathlib import PurePosixPath

from chem_vault.domain.shared.errors import ValidationError

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
