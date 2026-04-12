"""External vault client errors — port-level exceptions for vault interactions.

Defined in the application layer so both use cases and infrastructure
adapters can reference them without violating dependency direction.
"""


class VaultClientError(Exception):
    """Base error for external vault API interactions."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class VaultAuthError(VaultClientError):
    """Vault API key is invalid or expired (401/403)."""


class VaultNotFoundError(VaultClientError):
    """Requested vault resource not found (404)."""


class VaultConnectionError(VaultClientError):
    """Cannot reach external vault API."""
