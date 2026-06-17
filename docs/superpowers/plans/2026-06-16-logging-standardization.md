# Logging Standardization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Finish standardizing the backend on structlog and bring logging to a commercial baseline — one logger/event-name/level convention, env-driven level config, sensitive-data redaction, request-id + user/workspace correlation, and structured access logs.

**Architecture:** `infrastructure/logging.py` becomes a small package (settings, processors, context helpers, config assembly). A pure-ASGI `RequestContextMiddleware` (interface layer) binds a request id and emits a structured access log per request. The `get_auth` dependency binds user/workspace into the structlog context. Seven stdlib-logging files migrate to structlog; `%`-style call sites convert to event-name + kwargs.

**Tech Stack:** Python 3.13, structlog (already configured), pydantic-settings, FastAPI/Starlette ASGI, pytest + `uv`.

## Global Constraints

- Backend code only — no docker-compose / `.env` / dependency changes. (No new dependency is required; structlog + pydantic-settings are already present.)
- structlog is the framework (already chosen and configured). Do not introduce another.
- Public import path must stay stable: `from cellar.infrastructure.logging import configure_logging` must keep working after the module→package conversion.
- Layer rules: middleware lives in the **interface** layer; logging config/processors/settings live in **infrastructure**. Domain stays pure (no structlog in domain).
- Event-name convention: first positional arg = lowercase `snake_case`, dotted domain namespace (`noun.verb_outcome`). Data → kwargs only; never f-strings / `%` in the message. Use `logger.exception(...)` inside `except`.
- Redaction denylist (case-insensitive, substring): `password|passwd|secret|token|api_key|apikey|authorization|cookie|set-cookie|access_token|refresh_token|email|service_key|jwt|bearer`. Replacement string is exactly `***REDACTED***`. SMILES / molecule data / UUIDs are NOT redacted.
- Run tests from the `backend/` directory with `uv run pytest`.
- Every commit ends with the trailer: `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`. Use explicit pathspecs (`git commit ... -- <paths>`) — the working tree may hold unrelated staged work.
- Spec: `docs/superpowers/specs/2026-06-16-logging-standardization-design.md`.

---

## File Structure

**Create:**
- `backend/src/cellar/infrastructure/logging/__init__.py` — public API re-exports + conventions docstring
- `backend/src/cellar/infrastructure/logging/settings.py` — `LoggingSettings`
- `backend/src/cellar/infrastructure/logging/processors.py` — `redact_sensitive`
- `backend/src/cellar/infrastructure/logging/context.py` — `get_logger`, `bind_request_context`, `bind_user_context`, `clear_request_context`
- `backend/src/cellar/infrastructure/logging/config.py` — `configure_logging`, level application, noisy-logger defaults
- `backend/src/cellar/interface/middleware/__init__.py`
- `backend/src/cellar/interface/middleware/request_context.py` — `RequestContextMiddleware`
- Tests: `backend/tests/unit/infrastructure/logging/test_settings.py`, `test_processors.py`, `test_config.py`; `backend/tests/unit/interface/middleware/test_request_context.py`; `backend/tests/unit/interface/test_get_auth_binding.py`

**Delete:**
- `backend/src/cellar/infrastructure/logging.py` (replaced by the package)

**Modify:**
- `backend/src/cellar/interface/app.py` — call site for `configure_logging`, register middleware
- `backend/src/cellar/infrastructure/temporal/worker.py` — `configure_logging` call site + `%`-style call sites
- `backend/src/cellar/interface/dependencies/_core.py` — bind user/workspace in `get_auth`
- 7 sweep files (Task 7)

---

## Task 1: `LoggingSettings`

**Files:**
- Create: `backend/src/cellar/infrastructure/logging/__init__.py` (temporary minimal; expanded in Task 5)
- Create: `backend/src/cellar/infrastructure/logging/settings.py`
- Test: `backend/tests/unit/infrastructure/logging/test_settings.py`

> **Note:** Creating `logging/__init__.py` shadows the old `logging.py` for import. Do the conversion safely: in Step 0 below, `git rm` the old module and create the package dir. The old module's behavior is reconstructed across Tasks 1–5; until Task 5 lands, `configure_logging` is unavailable — that's fine because nothing is committed mid-task that imports it (app.py/worker.py call sites change in Task 5).

**Interfaces:**
- Produces: `LoggingSettings(BaseSettings)` with fields `level: str = "INFO"`, `format: str = "json"`, `level_overrides: dict[str, str] = {}`. Env vars: `LOG_LEVEL`, `LOG_FORMAT`, `LOG_LEVEL_OVERRIDES` (format `"name=LEVEL,name=LEVEL"`).

- [ ] **Step 0: Convert module → package**

```bash
cd backend
git rm src/cellar/infrastructure/logging.py
mkdir -p src/cellar/infrastructure/logging tests/unit/infrastructure/logging
touch tests/unit/infrastructure/logging/__init__.py
```

Create `src/cellar/infrastructure/logging/__init__.py` (minimal for now):

```python
"""Structured logging package (structlog). Public API re-exported here."""

from __future__ import annotations

from cellar.infrastructure.logging.settings import LoggingSettings

__all__ = ["LoggingSettings"]
```

- [ ] **Step 1: Write the failing test**

Create `tests/unit/infrastructure/logging/test_settings.py`:

```python
from __future__ import annotations

from cellar.infrastructure.logging.settings import LoggingSettings


def test_defaults():
    s = LoggingSettings(_env_file=None)
    assert s.level == "INFO"
    assert s.format == "json"
    assert s.level_overrides == {}


def test_reads_env(monkeypatch):
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    monkeypatch.setenv("LOG_FORMAT", "console")
    s = LoggingSettings(_env_file=None)
    assert s.level == "DEBUG"
    assert s.format == "console"


def test_level_overrides_parsed_from_string(monkeypatch):
    monkeypatch.setenv(
        "LOG_LEVEL_OVERRIDES",
        "sqlalchemy.engine=WARNING, cellar.infrastructure.temporal=DEBUG",
    )
    s = LoggingSettings(_env_file=None)
    assert s.level_overrides == {
        "sqlalchemy.engine": "WARNING",
        "cellar.infrastructure.temporal": "DEBUG",
    }


def test_level_overrides_empty_string():
    s = LoggingSettings(_env_file=None, level_overrides="")
    assert s.level_overrides == {}


def test_level_overrides_ignores_malformed_entries():
    s = LoggingSettings(_env_file=None, level_overrides="good=DEBUG,garbage,=,x=")
    assert s.level_overrides == {"good": "DEBUG"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/infrastructure/logging/test_settings.py -v`
Expected: FAIL — `ModuleNotFoundError: cellar.infrastructure.logging.settings`

- [ ] **Step 3: Write minimal implementation**

Create `src/cellar/infrastructure/logging/settings.py`:

```python
"""Logging configuration via environment variables."""

from __future__ import annotations

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class LoggingSettings(BaseSettings):
    """Typed logging configuration.

    Env vars (prefix ``LOG_``):
      - ``LOG_LEVEL``           root level (DEBUG/INFO/WARNING/ERROR/CRITICAL)
      - ``LOG_FORMAT``          ``json`` (prod) or ``console`` (dev)
      - ``LOG_LEVEL_OVERRIDES`` ``"name=LEVEL,name=LEVEL"`` per-logger overrides
    """

    model_config = SettingsConfigDict(env_prefix="LOG_", env_file=".env")

    level: str = "INFO"
    format: str = "json"
    level_overrides: dict[str, str] = {}

    @field_validator("level_overrides", mode="before")
    @classmethod
    def _parse_overrides(cls, value: object) -> object:
        """Accept ``"name=LEVEL,name=LEVEL"`` strings; pass dicts through."""
        if not isinstance(value, str):
            return value
        result: dict[str, str] = {}
        for pair in value.split(","):
            name, sep, lvl = pair.partition("=")
            name, lvl = name.strip(), lvl.strip()
            if sep and name and lvl:
                result[name] = lvl
        return result
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/infrastructure/logging/test_settings.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git commit -m "feat(logging): LoggingSettings with per-logger level overrides

Convert logging module to a package; add env-driven LoggingSettings
(LOG_LEVEL/LOG_FORMAT/LOG_LEVEL_OVERRIDES) parsing name=LEVEL pairs." \
  -m "Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>" \
  -- src/cellar/infrastructure/logging.py \
     src/cellar/infrastructure/logging/__init__.py \
     src/cellar/infrastructure/logging/settings.py \
     tests/unit/infrastructure/logging/__init__.py \
     tests/unit/infrastructure/logging/test_settings.py
```

---

## Task 2: `redact_sensitive` processor

**Files:**
- Create: `backend/src/cellar/infrastructure/logging/processors.py`
- Test: `backend/tests/unit/infrastructure/logging/test_processors.py`

**Interfaces:**
- Produces: `redact_sensitive(logger, method_name, event_dict) -> event_dict` (structlog processor signature). Module constants `REDACTED = "***REDACTED***"` and `SENSITIVE_KEY_RE`.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/infrastructure/logging/test_processors.py`:

```python
from __future__ import annotations

from cellar.infrastructure.logging.processors import REDACTED, redact_sensitive


def _run(event_dict):
    return redact_sensitive(None, "info", event_dict)


def test_redacts_top_level_sensitive_keys():
    out = _run({"event": "login", "password": "hunter2", "api_key": "abc"})
    assert out["password"] == REDACTED
    assert out["api_key"] == REDACTED
    assert out["event"] == "login"


def test_case_insensitive_and_substring():
    out = _run({"Authorization": "Bearer x", "user_email": "a@b.com"})
    assert out["Authorization"] == REDACTED
    assert out["user_email"] == REDACTED


def test_preserves_non_sensitive():
    out = _run({"molecule_id": "m-1", "smiles": "CCO", "workspace_id": "w-1"})
    assert out == {"molecule_id": "m-1", "smiles": "CCO", "workspace_id": "w-1"}


def test_recurses_into_nested_dicts_and_lists():
    out = _run(
        {
            "event": "call",
            "payload": {"token": "t", "nested": {"secret": "s"}},
            "items": [{"refresh_token": "r"}, {"name": "ok"}],
        }
    )
    assert out["payload"]["token"] == REDACTED
    assert out["payload"]["nested"]["secret"] == REDACTED
    assert out["items"][0]["refresh_token"] == REDACTED
    assert out["items"][1]["name"] == "ok"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/infrastructure/logging/test_processors.py -v`
Expected: FAIL — `ModuleNotFoundError: ...logging.processors`

- [ ] **Step 3: Write minimal implementation**

Create `src/cellar/infrastructure/logging/processors.py`:

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/infrastructure/logging/test_processors.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git commit -m "feat(logging): redact_sensitive processor (recursive key denylist)" \
  -m "Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>" \
  -- src/cellar/infrastructure/logging/processors.py \
     tests/unit/infrastructure/logging/test_processors.py
```

---

## Task 3: Context helpers (`get_logger`, bind/clear)

**Files:**
- Create: `backend/src/cellar/infrastructure/logging/context.py`
- Test: `backend/tests/unit/infrastructure/logging/test_processors.py` (append) — or a new `test_context.py`

**Interfaces:**
- Produces:
  - `get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger`
  - `bind_request_context(*, request_id: str, http_method: str, http_path: str) -> None`
  - `bind_user_context(*, user_id: str | None, workspace_id: str | None) -> None`
  - `clear_request_context() -> None`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/infrastructure/logging/test_context.py`:

```python
from __future__ import annotations

import structlog

from cellar.infrastructure.logging.context import (
    bind_request_context,
    bind_user_context,
    clear_request_context,
    get_logger,
)


def test_get_logger_returns_bound_logger():
    log = get_logger("x")
    assert hasattr(log, "info")


def test_bind_request_then_clear():
    clear_request_context()
    bind_request_context(request_id="r-1", http_method="GET", http_path="/m")
    ctx = structlog.contextvars.get_contextvars()
    assert ctx["request_id"] == "r-1"
    assert ctx["http_method"] == "GET"
    assert ctx["http_path"] == "/m"
    clear_request_context()
    assert structlog.contextvars.get_contextvars() == {}


def test_bind_user_skips_none():
    clear_request_context()
    bind_user_context(user_id="u-1", workspace_id=None)
    ctx = structlog.contextvars.get_contextvars()
    assert ctx["user_id"] == "u-1"
    assert "workspace_id" not in ctx
    clear_request_context()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/infrastructure/logging/test_context.py -v`
Expected: FAIL — `ModuleNotFoundError: ...logging.context`

- [ ] **Step 3: Write minimal implementation**

Create `src/cellar/infrastructure/logging/context.py`:

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/infrastructure/logging/test_context.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git commit -m "feat(logging): context helpers (get_logger + request/user binding)" \
  -m "Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>" \
  -- src/cellar/infrastructure/logging/context.py \
     tests/unit/infrastructure/logging/test_context.py
```

---

## Task 4: `configure_logging` (chain assembly + level application)

**Files:**
- Create: `backend/src/cellar/infrastructure/logging/config.py`
- Test: `backend/tests/unit/infrastructure/logging/test_config.py`

**Interfaces:**
- Consumes: `LoggingSettings` (Task 1), `redact_sensitive` (Task 2).
- Produces:
  - `DEFAULT_NOISY_LOGGERS: dict[str, str]`
  - `configure_logging(settings: LoggingSettings | None = None, *, extra_processors: list | None = None) -> None`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/infrastructure/logging/test_config.py`:

```python
from __future__ import annotations

import io
import json
import logging

import structlog

from cellar.infrastructure.logging.config import (
    DEFAULT_NOISY_LOGGERS,
    configure_logging,
)
from cellar.infrastructure.logging.settings import LoggingSettings


def test_configure_sets_root_level():
    configure_logging(LoggingSettings(_env_file=None, level="WARNING"))
    assert logging.getLogger().level == logging.WARNING


def test_noisy_loggers_muted_by_default():
    configure_logging(LoggingSettings(_env_file=None))
    for name in DEFAULT_NOISY_LOGGERS:
        assert logging.getLogger(name).level == logging.WARNING


def test_level_override_applied():
    configure_logging(
        LoggingSettings(_env_file=None, level_overrides={"sqlalchemy.engine": "ERROR"})
    )
    assert logging.getLogger("sqlalchemy.engine").level == logging.ERROR


def test_invalid_level_falls_back_to_info():
    configure_logging(LoggingSettings(_env_file=None, level="NOPE"))
    assert logging.getLogger().level == logging.INFO


def test_json_output_has_expected_keys(capsys):
    configure_logging(LoggingSettings(_env_file=None, format="json", level="INFO"))
    structlog.contextvars.clear_contextvars()
    structlog.get_logger("test").info("thing.happened", widget="w1", token="SECRET")
    out = capsys.readouterr().out.strip().splitlines()[-1]
    payload = json.loads(out)
    assert payload["event"] == "thing.happened"
    assert payload["level"] == "info"
    assert payload["widget"] == "w1"
    assert payload["token"] == "***REDACTED***"
    assert "timestamp" in payload
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/infrastructure/logging/test_config.py -v`
Expected: FAIL — `ModuleNotFoundError: ...logging.config`

- [ ] **Step 3: Write minimal implementation**

Create `src/cellar/infrastructure/logging/config.py`:

```python
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
```

> **Console exceptions:** `dict_tracebacks` is added only in JSON mode. In console mode, `ConsoleRenderer` formats exceptions itself (idiomatic structlog) — this is the deliberate refinement of the spec's "console uses format_exc_info" line. Redaction still runs before the renderer in both modes.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/infrastructure/logging/test_config.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git commit -m "feat(logging): configure_logging — hardened chain, levels, redaction

Adds callsite info + UTC ISO timestamps + structured tracebacks, redaction on
native AND foreign logs (foreign_pre_chain), noisy-lib defaults, per-logger
overrides, and an extra_processors hook for future trace-id correlation." \
  -m "Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>" \
  -- src/cellar/infrastructure/logging/config.py \
     tests/unit/infrastructure/logging/test_config.py
```

---

## Task 5: Finalize package API + update call sites

**Files:**
- Modify: `backend/src/cellar/infrastructure/logging/__init__.py`
- Modify: `backend/src/cellar/interface/app.py:24-30`
- Modify: `backend/src/cellar/infrastructure/temporal/worker.py:26-29`

**Interfaces:**
- Produces: package public API — `configure_logging`, `LoggingSettings`, `get_logger`, `bind_request_context`, `bind_user_context`, `clear_request_context`, `redact_sensitive`.

- [ ] **Step 1: Expand `__init__.py` with full re-exports + conventions docstring**

Replace `src/cellar/infrastructure/logging/__init__.py` with:

```python
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
automatically by the ``redact_sensitive`` processor.
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
```

- [ ] **Step 2: Update `app.py` call site**

In `src/cellar/interface/app.py`, the lifespan currently has (lines ~24-30):

```python
        # Structured logging
        import os

        configure_logging(
            json_output=os.getenv("LOG_FORMAT", "json") == "json",
            log_level=os.getenv("LOG_LEVEL", "INFO"),
        )
```

Replace with:

```python
        # Structured logging (reads LOG_LEVEL / LOG_FORMAT / LOG_LEVEL_OVERRIDES)
        configure_logging()
```

(The `import os` here was only for the logging call; other code in `create_app` re-imports `os` locally at line ~206, so this removal is safe. Verify with `grep -n "import os" src/cellar/interface/app.py` — the lifespan-local one is the only one to remove.)

- [ ] **Step 3: Update `worker.py` call site**

In `src/cellar/infrastructure/temporal/worker.py` lines ~26-29:

```python
    configure_logging(
        json_output=os.getenv("LOG_FORMAT", "json") == "json",
        log_level=os.getenv("LOG_LEVEL", "INFO"),
    )
```

Replace with:

```python
    configure_logging()
```

Remove the now-unused `import os` in worker.py **only if** no other usage remains (`grep -n "os\." src/cellar/infrastructure/temporal/worker.py`). If `os` is used elsewhere, leave the import.

- [ ] **Step 4: Run the full unit suite + import smoke check**

Run:
```bash
uv run python -c "import cellar.interface.app; import cellar.infrastructure.temporal.worker; print('import OK')"
uv run pytest tests/unit/infrastructure/logging -v
```
Expected: `import OK`, and all logging unit tests PASS.

- [ ] **Step 5: Commit**

```bash
git commit -m "refactor(logging): finalize package API + switch call sites to LoggingSettings" \
  -m "Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>" \
  -- src/cellar/infrastructure/logging/__init__.py \
     src/cellar/interface/app.py \
     src/cellar/infrastructure/temporal/worker.py
```

---

## Task 6: `RequestContextMiddleware`

**Files:**
- Create: `backend/src/cellar/interface/middleware/__init__.py` (empty)
- Create: `backend/src/cellar/interface/middleware/request_context.py`
- Modify: `backend/src/cellar/interface/app.py` (register middleware after CORS)
- Test: `backend/tests/unit/interface/middleware/test_request_context.py`

**Interfaces:**
- Consumes: `bind_request_context`, `clear_request_context`, `get_logger` (Tasks 3/5).
- Produces: `class RequestContextMiddleware` (pure ASGI; `__init__(self, app)`, `async def __call__(self, scope, receive, send)`).

- [ ] **Step 1: Write the failing test**

Create `tests/unit/interface/middleware/__init__.py` (empty) and `tests/unit/interface/middleware/test_request_context.py`:

```python
from __future__ import annotations

import structlog
from starlette.applications import Starlette
from starlette.responses import PlainTextResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from cellar.infrastructure.logging.config import configure_logging
from cellar.infrastructure.logging.settings import LoggingSettings
from cellar.interface.middleware.request_context import RequestContextMiddleware


def _client():
    async def ok(request):
        # prove request_id is visible downstream via contextvars
        rid = structlog.contextvars.get_contextvars().get("request_id")
        return PlainTextResponse(rid or "none")

    async def boom(request):
        raise RuntimeError("kaboom")

    app = Starlette(
        routes=[Route("/ok", ok), Route("/boom", boom), Route("/health", ok)]
    )
    app.add_middleware(RequestContextMiddleware)
    return TestClient(app, raise_server_exceptions=False)


def test_mints_request_id_and_echoes_header():
    r = _client().get("/ok")
    assert r.status_code == 200
    assert r.headers["x-request-id"]
    assert r.text == r.headers["x-request-id"]  # same id downstream


def test_passes_through_supplied_request_id():
    r = _client().get("/ok", headers={"X-Request-ID": "abc-123"})
    assert r.headers["x-request-id"] == "abc-123"
    assert r.text == "abc-123"


def test_access_log_emitted_with_fields():
    configure_logging(LoggingSettings(_env_file=None, format="json"))
    with structlog.testing.capture_logs() as logs:
        _client().get("/ok")
    completed = [e for e in logs if e["event"] == "request.completed"]
    assert completed
    entry = completed[0]
    assert entry["method"] == "GET"
    assert entry["path"] == "/ok"
    assert entry["status_code"] == 200
    assert "duration_ms" in entry


def test_health_excluded_from_access_log():
    with structlog.testing.capture_logs() as logs:
        _client().get("/health")
    assert not [e for e in logs if e["event"] == "request.completed"]


def test_context_cleared_after_request():
    structlog.contextvars.clear_contextvars()
    _client().get("/ok")
    assert structlog.contextvars.get_contextvars() == {}


def test_clears_context_even_on_error():
    structlog.contextvars.clear_contextvars()
    r = _client().get("/boom")
    assert r.status_code == 500
    assert structlog.contextvars.get_contextvars() == {}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/interface/middleware/test_request_context.py -v`
Expected: FAIL — `ModuleNotFoundError: ...interface.middleware.request_context`

- [ ] **Step 3: Write minimal implementation**

Create `src/cellar/interface/middleware/__init__.py` (empty file) and `src/cellar/interface/middleware/request_context.py`:

```python
"""Pure-ASGI middleware: per-request id, structured access log, context cleanup."""

from __future__ import annotations

import time
import uuid
from typing import Any

from cellar.infrastructure.logging import (
    bind_request_context,
    clear_request_context,
    get_logger,
)

logger = get_logger(__name__)

_ACCESS_LOG_EXCLUDE = frozenset({"/health"})


class RequestContextMiddleware:
    """Bind a request id (+method/path) for the whole request, log completion.

    Pure ASGI (not ``BaseHTTPMiddleware``) so contextvars bound here propagate
    downstream and are reliably cleared in ``finally``.
    """

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: dict, receive: Any, send: Any) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = {k.decode().lower(): v.decode() for k, v in scope.get("headers", [])}
        request_id = headers.get("x-request-id") or str(uuid.uuid4())
        method = scope.get("method", "")
        path = scope.get("path", "")
        client = scope.get("client")
        client_ip = client[0] if client else None

        bind_request_context(
            request_id=request_id, http_method=method, http_path=path
        )
        status_holder: dict[str, int] = {"status": 0}
        start = time.monotonic()

        async def send_wrapper(message: dict) -> None:
            if message["type"] == "http.response.start":
                status_holder["status"] = message["status"]
                headers_list = message.setdefault("headers", [])
                headers_list.append((b"x-request-id", request_id.encode()))
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            if path not in _ACCESS_LOG_EXCLUDE:
                state = scope.get("state") or {}
                duration_ms = round((time.monotonic() - start) * 1000, 2)
                logger.info(
                    "request.completed",
                    request_id=request_id,
                    method=method,
                    path=path,
                    status_code=status_holder["status"],
                    duration_ms=duration_ms,
                    client_ip=client_ip,
                    user_id=state.get("user_id"),
                    workspace_id=state.get("workspace_id"),
                )
            clear_request_context()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/interface/middleware/test_request_context.py -v`
Expected: PASS (6 passed)

- [ ] **Step 5: Register the middleware in `app.py`**

In `src/cellar/interface/app.py`, after the CORS block (lines ~205-215), add the import near the top with the other interface imports:

```python
from cellar.interface.middleware.request_context import RequestContextMiddleware
```

and register it AFTER the CORS `add_middleware` call so it becomes the outermost layer (Starlette runs the last-added middleware first):

```python
    # Request context — outermost, so request_id wraps everything incl. CORS.
    app.add_middleware(RequestContextMiddleware)
```

- [ ] **Step 6: Verify app still imports and unit suite passes**

Run:
```bash
uv run python -c "import cellar.interface.app; print('app import OK')"
uv run pytest tests/unit/interface/middleware -v
```
Expected: `app import OK`, tests PASS.

- [ ] **Step 7: Commit**

```bash
git commit -m "feat(logging): RequestContextMiddleware — request id + structured access log" \
  -m "Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>" \
  -- src/cellar/interface/middleware/__init__.py \
     src/cellar/interface/middleware/request_context.py \
     src/cellar/interface/app.py \
     tests/unit/interface/middleware/__init__.py \
     tests/unit/interface/middleware/test_request_context.py
```

---

## Task 7: Bind user/workspace at the `get_auth` chokepoint

**Files:**
- Modify: `backend/src/cellar/interface/dependencies/_core.py:150-152`
- Test: `backend/tests/unit/interface/test_get_auth_binding.py`

**Interfaces:**
- Consumes: `bind_user_context` (Task 3/5).
- Modifies `get_auth` to also accept `request: Request` and bind user/workspace into contextvars + `request.state`.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/interface/test_get_auth_binding.py`:

```python
from __future__ import annotations

import asyncio
from types import SimpleNamespace

import structlog
from starlette.requests import Request

from cellar.interface.dependencies._core import get_auth


def _make_request() -> Request:
    return Request({"type": "http", "headers": [], "state": {}})


def test_get_auth_binds_user_and_workspace():
    structlog.contextvars.clear_contextvars()
    request = _make_request()
    auth = SimpleNamespace(user_id="u-1", workspace_id="w-1")
    result = asyncio.run(get_auth(request, auth))
    assert result is auth
    ctx = structlog.contextvars.get_contextvars()
    assert ctx["user_id"] == "u-1"
    assert ctx["workspace_id"] == "w-1"
    assert request.state.user_id == "u-1"
    assert request.state.workspace_id == "w-1"
    structlog.contextvars.clear_contextvars()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/interface/test_get_auth_binding.py -v`
Expected: FAIL — `TypeError: get_auth() takes 1 positional argument but 2 were given`

- [ ] **Step 3: Update `get_auth`**

In `src/cellar/interface/dependencies/_core.py`, add the imports near the top (with existing `from fastapi import Depends, Request` — `Request` is already imported):

```python
from cellar.infrastructure.logging import bind_user_context
```

Replace the existing `get_auth` (lines ~150-152):

```python
async def get_auth(auth: Annotated[Any, Depends(_sentinel_get_auth)]) -> Any:
    """Stable auth dependency wrapper — overridable via dependency_overrides."""
    return auth
```

with:

```python
async def get_auth(
    request: Request,
    auth: Annotated[Any, Depends(_sentinel_get_auth)],
) -> Any:
    """Stable auth dependency wrapper — overridable via dependency_overrides.

    Also binds the authenticated user/workspace into the logging context and
    onto ``request.state`` so the access-log line can include them.
    """
    user_id = getattr(auth, "user_id", None)
    workspace_id = getattr(auth, "workspace_id", None)
    user_id = str(user_id) if user_id is not None else None
    workspace_id = str(workspace_id) if workspace_id is not None else None
    bind_user_context(user_id=user_id, workspace_id=workspace_id)
    request.state.user_id = user_id
    request.state.workspace_id = workspace_id
    return auth
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/interface/test_get_auth_binding.py -v`
Expected: PASS

Also run a broader check that auth-dependent API tests still pass (the signature gained a `Request` param, which FastAPI injects automatically):
```bash
uv run pytest tests/api -k "auth or workspace" -q
```
Expected: no new failures (record any pre-existing failures in `docs/backlog/` rather than fixing inline).

- [ ] **Step 5: Commit**

```bash
git commit -m "feat(logging): bind user/workspace into log context at get_auth chokepoint" \
  -m "Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>" \
  -- src/cellar/interface/dependencies/_core.py \
     tests/unit/interface/test_get_auth_binding.py
```

---

## Task 8: Standardization sweep (stdlib → structlog + call-site style)

Mechanical migration of 7 stdlib-logging files + `worker.py` call sites. Each file:
the `import logging` → removed (unless used for level constants), `logger = logging.getLogger(__name__)` → `logger = structlog.get_logger(__name__)` (add `import structlog`), and each call site converted to event-name + kwargs.

**Files:**
- Modify: `application/attachment/delete_attachment.py`
- Modify: `application/cdd_import/get_cdd_molecule_import_runtime_status.py`
- Modify: `application/cdd_import/get_cdd_plate_import_runtime_status.py`
- Modify: `application/chemical_registration/bulk_registration_service.py`
- Modify: `infrastructure/persistence/unit_of_work.py`
- Modify: `infrastructure/temporal/orchestrators/cdd_molecule_import.py`
- Modify: `infrastructure/temporal/orchestrators/cdd_plate_import.py`
- Modify: `infrastructure/temporal/worker.py`

> No new unit test file — these are call-site migrations covered by existing tests for those modules. After each edit, run that module's existing tests. Verify no `logging.getLogger` / `%`-style log calls remain at the end (Step final).

- [ ] **Step 1: `delete_attachment.py`**

Remove `import logging`, add `import structlog`. Change `logger = logging.getLogger(__name__)` → `logger = structlog.get_logger(__name__)`. Convert line ~57:

```python
                logger.warning("Failed to delete blob %s", attachment.storage_key, exc_info=True)
```
→
```python
                logger.warning(
                    "attachment.blob_delete_failed",
                    storage_key=attachment.storage_key,
                    exc_info=True,
                )
```

- [ ] **Step 2: `get_cdd_molecule_import_runtime_status.py`**

Swap logger import/factory as above. Convert lines ~87-90:

```python
            logger.warning(
                "orchestrator_get_progress_failed: workflow_id=%s — falling back to DB",
                input.workflow_id,
            )
```
→
```python
            logger.warning(
                "cdd_molecule_import.progress_failed_fallback_to_db",
                workflow_id=input.workflow_id,
            )
```

- [ ] **Step 3: `get_cdd_plate_import_runtime_status.py`**

Swap logger import/factory. Convert lines ~75-78 identically but namespaced for plates:

```python
            logger.warning(
                "cdd_plate_import.progress_failed_fallback_to_db",
                workflow_id=input.workflow_id,
            )
```

- [ ] **Step 4: `bulk_registration_service.py`**

Swap logger import/factory. Convert lines ~439-445:

```python
            logger.warning(
                "Batch creation failed for molecule %s row %d: %s",
                molecule.id,
                item.row_index,
                err,
            )
```
→
```python
            logger.warning(
                "bulk_registration.batch_create_failed",
                molecule_id=str(molecule.id),
                row_index=item.row_index,
                error=str(err),
            )
```

- [ ] **Step 5: `unit_of_work.py`**

Swap logger import/factory. Convert line ~91:

```python
                logger.exception("UnitOfWork rollback failed during __aexit__")
```
→
```python
                logger.exception("unit_of_work.rollback_failed")
```

- [ ] **Step 6: `orchestrators/cdd_molecule_import.py`**

Swap logger import/factory. Convert lines ~82-85:

```python
                logger.warning(
                    "temporal_describe_failed: workflow_id=%s",
                    workflow_id,
                )
```
→
```python
                logger.warning(
                    "temporal.describe_failed",
                    workflow_id=workflow_id,
                )
```

- [ ] **Step 7: `orchestrators/cdd_plate_import.py`**

Identical change to Step 6 (same `temporal.describe_failed` event, `workflow_id=workflow_id`).

- [ ] **Step 8: `worker.py` call-site style (already structlog)**

Convert lines ~32-37:

```python
    logger.info(
        "Connecting to Temporal at %s (namespace=%s, queue=%s)",
        settings.address,
        settings.namespace,
        settings.task_queue,
    )
```
→
```python
    logger.info(
        "temporal.connecting",
        address=settings.address,
        namespace=settings.namespace,
        queue=settings.task_queue,
    )
```

Convert line ~250:

```python
    logger.info("Temporal worker started on queue %r", settings.task_queue)
```
→
```python
    logger.info("temporal.worker_started", queue=settings.task_queue)
```

- [ ] **Step 9: Verify no holdouts remain**

Run:
```bash
cd backend
grep -rn "logging.getLogger" src/cellar && echo "HOLDOUTS FOUND" || echo "no stdlib getLogger"
grep -rnE 'logger\.(info|warning|error|debug|exception)\([^)]*%[sdr]' src/cellar && echo "PERCENT-STYLE FOUND" || echo "no percent-style log calls"
uv run pytest tests/unit -q
```
Expected: `no stdlib getLogger`, `no percent-style log calls`, unit tests green.

- [ ] **Step 10: Commit**

```bash
git commit -m "refactor(logging): migrate 7 stdlib loggers to structlog + event-name call sites

Standardizes all backend logging on structlog with snake_case dotted event
names and kwargs; removes the last logging.getLogger holdouts and %-style
log messages." \
  -m "Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>" \
  -- src/cellar/application/attachment/delete_attachment.py \
     src/cellar/application/cdd_import/get_cdd_molecule_import_runtime_status.py \
     src/cellar/application/cdd_import/get_cdd_plate_import_runtime_status.py \
     src/cellar/application/chemical_registration/bulk_registration_service.py \
     src/cellar/infrastructure/persistence/unit_of_work.py \
     src/cellar/infrastructure/temporal/orchestrators/cdd_molecule_import.py \
     src/cellar/infrastructure/temporal/orchestrators/cdd_plate_import.py \
     src/cellar/infrastructure/temporal/worker.py
```

---

## Task 9: Full-suite verification + lint

**Files:** none (verification only).

- [ ] **Step 1: Run the full backend unit + api suites**

```bash
cd backend
uv run pytest tests/unit tests/api -q
```
Expected: all green, or only pre-existing failures unrelated to logging (record those in `docs/backlog/` with root cause — do not fix inline).

- [ ] **Step 2: Lint / format the touched files**

```bash
uv run ruff check src/cellar/infrastructure/logging src/cellar/interface/middleware src/cellar/interface/dependencies/_core.py
uv run ruff format --check src/cellar/infrastructure/logging src/cellar/interface/middleware
```
Expected: clean (fix any reported issues, then re-run).

- [ ] **Step 3: Manual smoke (optional, recommended)**

```bash
LOG_FORMAT=json uv run python -c "
from cellar.infrastructure.logging import configure_logging, get_logger, bind_request_context
configure_logging()
bind_request_context(request_id='demo', http_method='GET', http_path='/x')
get_logger('smoke').info('demo.event', widget='w', password='SHOULD_HIDE')
"
```
Expected: one JSON line with `request_id="demo"`, `event="demo.event"`, `password="***REDACTED***"`, a `timestamp`, `func_name`, and `lineno`.

- [ ] **Step 4: Update spec status**

Mark the spec (`docs/superpowers/specs/2026-06-16-logging-standardization-design.md`) status line to `Implemented` and commit:

```bash
git commit -m "docs(logging): mark logging-standardization spec implemented" \
  -m "Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>" \
  -- docs/superpowers/specs/2026-06-16-logging-standardization-design.md
```
(Use `git add -f` first if git reports the path ignored.)

---

## Self-Review Notes (author)

- **Spec coverage:** §3 package → Tasks 1–5; §4 settings/levels → Tasks 1,4; §5 chain → Task 4; §6 redaction → Task 2 (+ applied in 4); §7.1 middleware → Task 6; §7.2 user/workspace → Task 7; §8 sweep → Task 8; §9 conventions → `__init__.py` docstring (Task 5) + applied in Task 8; §10 testing → Tasks 1–7 tests + Task 9. All covered.
- **Type consistency:** `redact_sensitive`, `configure_logging(settings, *, extra_processors)`, `get_logger`, `bind_request_context(request_id, http_method, http_path)`, `bind_user_context(user_id, workspace_id)`, `clear_request_context`, `RequestContextMiddleware(app)` — names identical across producing/consuming tasks.
- **Made-ready hook:** `extra_processors` param present (Task 4) for future Sentry/OTel trace-id processor; no SaaS wired (out of scope).
