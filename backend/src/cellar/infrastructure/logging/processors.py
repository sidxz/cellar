"""structlog processors. ``redact_sensitive`` scrubs PII/secret values."""

from __future__ import annotations

import re
from typing import Any

REDACTED = "***REDACTED***"

SENSITIVE_KEY_RE = re.compile(
    r"password|passwd|secret|token|api_?key|authorization|cookie|set-cookie"
    r"|access_token|refresh_token|email|service_key|jwt|bearer",
    re.IGNORECASE,
)


def _redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            k: (REDACTED if SENSITIVE_KEY_RE.search(str(k)) else _redact(v))
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [_redact(v) for v in value]
    if isinstance(value, tuple):
        return tuple(_redact(v) for v in value)
    return value


def redact_sensitive(
    _logger: Any, _method_name: str, event_dict: dict[str, Any]
) -> dict[str, Any]:
    """Replace values of sensitive-looking keys with ``REDACTED`` (recursive)."""
    return {
        k: (REDACTED if SENSITIVE_KEY_RE.search(str(k)) else _redact(v))
        for k, v in event_dict.items()
    }
