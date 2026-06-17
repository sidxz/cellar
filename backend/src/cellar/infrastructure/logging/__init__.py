"""Structured logging for Cellar (structlog).

Call ``configure_logging()`` once at startup, then ``get_logger(__name__)``.

Logging conventions (enforced across the backend):
  - Event name = first positional arg: lowercase snake_case, dotted namespace
    (``noun.verb_outcome``) — e.g. ``export.skipped``, ``async_job.not_found``.
  - Pass data as keyword args ONLY. Never f-strings or %-formatting.
  - Use ``logger.exception("event.failed", ...)`` inside ``except`` blocks.
  - Levels: DEBUG dev detail · INFO state/business events · WARNING degraded
    /recoverable · ERROR failed op needing attention · CRITICAL app failure.

Sensitive values (keys matching the redaction denylist) are scrubbed
automatically by the ``redact_sensitive`` processor. Redaction is KEY-based:
pass sensitive data as a denylisted kwarg (e.g. ``token=``) so it is scrubbed
— a secret string-formatted into the event message itself is NOT scrubbed.
"""

from __future__ import annotations

from cellar.infrastructure.logging.config import configure_logging
from cellar.infrastructure.logging.context import (
    bind_request_context,
    bind_user_context,
    clear_request_context,
    get_logger,
)
from cellar.infrastructure.logging.processors import redact_sensitive
from cellar.infrastructure.logging.settings import LoggingSettings

__all__ = [
    "LoggingSettings",
    "bind_request_context",
    "bind_user_context",
    "clear_request_context",
    "configure_logging",
    "get_logger",
    "redact_sensitive",
]
