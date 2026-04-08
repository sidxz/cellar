"""CDD Vault client errors — infrastructure-layer exceptions."""


class CddClientError(Exception):
    """Base error for CDD Vault API interactions."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class CddAuthError(CddClientError):
    """CDD API key is invalid or expired (401/403)."""


class CddNotFoundError(CddClientError):
    """Requested CDD resource not found (404)."""


class CddConnectionError(CddClientError):
    """Cannot reach CDD Vault API."""
