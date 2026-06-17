"""structlog + stdlib-bridge configuration. Call ``configure_logging()`` once."""

from __future__ import annotations

import logging
import sys

import structlog
from structlog.processors import CallsiteParameter

from cellar.infrastructure.logging.processors import redact_sensitive
from cellar.infrastructure.logging.settings import LoggingSettings

# Third-party loggers quieted to WARNING unless overridden.
DEFAULT_NOISY_LOGGERS: dict[str, str] = {
    "uvicorn.access": "WARNING",
    "sqlalchemy.engine": "WARNING",
    "httpx": "WARNING",
    "asyncpg": "WARNING",
    "temporalio": "WARNING",
    "redis": "WARNING",
    "alembic": "WARNING",
}


def _coerce_level(name: str) -> int:
    """Map a level name to its int; fall back to INFO and warn on a bad name."""
    level = getattr(logging, name.upper(), None)
    if isinstance(level, int):
        return level
    structlog.get_logger("cellar.logging").warning(
        "log.invalid_level", requested=name, fallback="INFO"
    )
    return logging.INFO


def configure_logging(
    settings: LoggingSettings | None = None,
    *,
    extra_processors: list | None = None,
) -> None:
    """Configure structlog with JSON (prod) or console (dev) output.

    Idempotent: clears existing root handlers first.
    ``extra_processors`` is the made-ready hook for a future trace-id processor
    (Sentry/OTel); inserted just before redaction.
    """
    settings = settings or LoggingSettings()
    json_output = settings.format == "json"
    timestamper = structlog.processors.TimeStamper(fmt="iso", utc=True)

    # Processors shared by structlog-native and foreign (stdlib) records, so
    # third-party logs also get timestamps, levels, and REDACTION.
    pre_chain: list = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.PositionalArgumentsFormatter(),
        timestamper,
        structlog.processors.StackInfoRenderer(),
    ]
    if json_output:
        pre_chain.append(structlog.processors.dict_tracebacks)
    pre_chain.extend(extra_processors or [])
    pre_chain.append(redact_sensitive)

    structlog_processors: list = [
        *pre_chain[:-1],  # everything except redact (re-add after callsite)
        structlog.processors.CallsiteParameterAdder(
            {CallsiteParameter.FUNC_NAME, CallsiteParameter.LINENO}
        ),
        redact_sensitive,
        structlog.processors.UnicodeDecoder(),
        structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
    ]

    structlog.configure(
        processors=structlog_processors,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    renderer = (
        structlog.processors.JSONRenderer()
        if json_output
        else structlog.dev.ConsoleRenderer()
    )
    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=pre_chain,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(_coerce_level(settings.level))

    applied = {**DEFAULT_NOISY_LOGGERS, **settings.level_overrides}
    for name, lvl in applied.items():
        logging.getLogger(name).setLevel(_coerce_level(lvl))
