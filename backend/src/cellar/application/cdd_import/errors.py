"""CDD Vault client errors — port-level exceptions for CDD interactions.

Defined in the application layer so both use cases and infrastructure
adapters can reference them without violating dependency direction.
"""


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


class CddRateLimitError(CddClientError):
    """CDD API rate limit exceeded (429). Retryable after ``retry_after`` seconds."""

    def __init__(self, message: str, retry_after: int = 60) -> None:
        super().__init__(message, status_code=429)
        self.retry_after = retry_after
