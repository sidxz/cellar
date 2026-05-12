"""Domain protocol for secrets storage.

The domain layer defines this protocol; infrastructure provides implementations
(e.g. Infisical, environment variables). Domain and application layers depend
only on this protocol — never on concrete providers.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class SecretProvider(Protocol):
    """Pluggable interface for reading/writing secret values."""

    async def get_secret(self, key: str) -> str | None:
        """Retrieve a secret by key. Returns None if not found."""
        ...

    async def set_secret(self, key: str, value: str) -> None:
        """Store or overwrite a secret value."""
        ...

    async def delete_secret(self, key: str) -> None:
        """Remove a secret by key. No-op if not found."""
        ...
