"""Logger access + request/user context binding (structlog contextvars)."""

from __future__ import annotations

import structlog


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """Return a structlog logger. Standard call: ``get_logger(__name__)``."""
    return structlog.get_logger(name)


def bind_request_context(
    *, request_id: str, http_method: str, http_path: str
) -> None:
    """Bind per-request fields so every downstream log carries them."""
    structlog.contextvars.bind_contextvars(
        request_id=request_id, http_method=http_method, http_path=http_path
    )


def bind_user_context(*, user_id: str | None, workspace_id: str | None) -> None:
    """Bind authenticated user/workspace once auth resolves. Skips None values."""
    fields = {}
    if user_id is not None:
        fields["user_id"] = user_id
    if workspace_id is not None:
        fields["workspace_id"] = workspace_id
    if fields:
        structlog.contextvars.bind_contextvars(**fields)


def clear_request_context() -> None:
    """Clear all structlog contextvars (call at end of every request)."""
    structlog.contextvars.clear_contextvars()
