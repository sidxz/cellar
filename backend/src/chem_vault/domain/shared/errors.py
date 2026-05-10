"""Domain error hierarchy.

DomainError
├── NotFoundError
├── ConflictError
├── ConcurrencyConflictError
├── ValidationError
├── AuthorizationError
└── DataLockedError
"""

from __future__ import annotations

from typing import Any


class DomainError(Exception):
    """Base domain error. All domain failures derive from this."""

    def __init__(self, message: str, *, detail: str | None = None) -> None:
        self.message = message
        self.detail = detail
        super().__init__(message)

    def body_extras(self) -> dict[str, Any]:
        """Optional override hook for subclasses that need extra JSON fields.

        Returned keys are merged into the HTTP error body. Used by errors that
        carry structured payloads (e.g. blocker lists for cascade-restrict).
        """
        return {}


class NotFoundError(DomainError):
    """Raised when a requested entity does not exist."""

    def __init__(
        self,
        entity_type: str,
        entity_id: str | None = None,
        *,
        detail: str | None = None,
    ) -> None:
        self.entity_type = entity_type
        self.entity_id = entity_id
        msg = f"{entity_type} not found"
        if entity_id:
            msg = f"{entity_type} '{entity_id}' not found"
        super().__init__(msg, detail=detail)


class ConflictError(DomainError):
    """Raised when an operation violates a business rule or uniqueness constraint."""


class ConcurrencyConflictError(DomainError):
    """Raised when optimistic concurrency check fails (version mismatch)."""

    def __init__(
        self,
        entity_type: str,
        entity_id: str,
        *,
        detail: str | None = None,
    ) -> None:
        self.entity_type = entity_type
        self.entity_id = entity_id
        super().__init__(
            f"Concurrency conflict on {entity_type} '{entity_id}': "
            "entity was modified by another transaction",
            detail=detail,
        )


class ValidationError(DomainError):
    """Raised when a domain invariant is violated."""


class AuthorizationError(DomainError):
    """Raised when the caller lacks required permissions."""


class DataLockedError(DomainError):
    """Raised when attempting to modify a locked entity (e.g., locked Run data)."""


class ServiceUnavailableError(DomainError):
    """Raised when an external service required by the operation is unreachable.

    Maps to HTTP 503. Use sparingly — most failures should be domain-specific
    errors (NotFound, Conflict, etc.); this is for genuine "the dependency
    isn't there right now" situations such as a missing workflow engine.
    """
