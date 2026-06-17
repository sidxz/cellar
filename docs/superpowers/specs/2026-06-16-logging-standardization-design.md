# Logging Standardization — Commercial-Grade Structured Logging

**Date:** 2026-06-16
**Branch:** design-7
**Status:** Approved design → ready for implementation plan
**Scope tier:** Tier 2 (standardize + request observability) + sensitive-data redaction. Backend code only.

---

## 1. Problem & Goal

Logging across the backend is inconsistent and below commercial-grade. `structlog` is already
the chosen framework (configured in `infrastructure/logging.py`, used by ~64% of logging code),
but:

- **Two logger-obtain patterns coexist** — 22 files use `structlog.get_logger(__name__)`, 7 files
  use `logging.getLogger(__name__)` with `%`-style / f-string formatting that loses structure in
  production JSON.
- **Correlation-ID helpers exist but are dead code** — `bind_correlation_id()` / `clear_contextvars()`
  are never called. No request middleware exists at all (no request ID, no access logs).
- **No env-tiered level config** — only a flat `LOG_LEVEL`; only three noisy third-party loggers are
  muted; `asyncpg`, `temporalio`, `redis`, `alembic` are unhandled.
- **No PII/secret redaction** — raw emails, tokens, service keys, UUIDs, file paths go to logs
  (relevant for a 21 CFR Part 11 app).
- **Observability stack unwired** — Sentry/Tempo/Prometheus are in the stack docs but nothing is imported.
- **Event names are ad hoc** — `"async_job_not_found"` vs `"export.skip_non_runnable"` vs
  `"Failed to delete blob %s"`.

**Goal:** Finish standardizing on structlog and bring logging to a commercial baseline — one logger
convention, one event-name/level convention, request-scoped correlation (request ID + user/workspace),
structured access logs, sensitive-data redaction, and env-driven level configuration — without wiring
the external observability SaaS yet (made-ready, not wired).

**Framework decision:** structlog is already in the stack and configured. This is **not** a framework
selection — it is finishing the migration onto structlog and hardening the configuration.

---

## 2. Scope

**In scope (Tier 2 + redaction, backend code only):**
1. Convert `infrastructure/logging.py` into a small focused package.
2. `LoggingSettings` (pydantic-settings) — root level, format, per-logger overrides, noisy-lib defaults.
3. Hardened processor chain (callsite info, UTC ISO timestamps, exception formatting, redaction).
4. `redact_sensitive` processor (key denylist, recursive).
5. `RequestContextMiddleware` (interface layer, pure ASGI) — request ID, timing, structured access log,
   `X-Request-ID` echo, guaranteed context cleanup.
6. User/workspace binding at the `get_auth` chokepoint.
7. Standardization sweep — migrate the 7 stdlib files to structlog; fix `%`-style call sites
   (including `worker.py`).
8. Documented event-name + level conventions.
9. Unit tests for redaction, settings parsing, middleware, JSON output.

**Out of scope (made-ready, not wired):**
- Sentry SDK init / FastAPI integration.
- OpenTelemetry / Grafana Tempo trace-id correlation.
- Prometheus `/metrics`.
- File output / log rotation (stdout only — container/orchestrator captures it).
- docker-compose / `.env` / dependency changes (unless a strictly-required dep emerges; none expected).

---

## 3. Architecture & Layering

### 3.1 Logging package (infrastructure layer)

`infrastructure/logging.py` → `infrastructure/logging/` (public API stays import-compatible:
`from cellar.infrastructure.logging import configure_logging` keeps working via `__init__.py`):

```
infrastructure/logging/
  __init__.py     # public API re-exports
  config.py       # configure_logging(), processor-chain assembly, level application
  settings.py     # LoggingSettings(BaseSettings)
  processors.py   # redact_sensitive processor
  context.py      # get_logger, bind_request_context, bind_user_context, clear_request_context
```

Rationale: the module is outgrowing one file once settings + redaction + context helpers land.
Matches the existing per-subsystem `settings.py` convention (`temporal/settings.py`,
`sentinel/settings.py`, `persistence/settings.py`).

### 3.2 Request middleware (interface layer)

`interface/middleware/request_context.py` — `RequestContextMiddleware`. A request/ASGI concern, so it
belongs in the interface layer. Interface may depend on infrastructure, so it calls the logging
context helpers. Respects the project layer rules.

---

## 4. Configuration & Log Levels — `LoggingSettings`

Pydantic-settings model, env-driven (no compose changes):

| Field | Env var | Default | Notes |
|-------|---------|---------|-------|
| `log_level` | `LOG_LEVEL` | `INFO` | Root level (DEBUG/INFO/WARNING/ERROR/CRITICAL) |
| `log_format` | `LOG_FORMAT` | `json` | `json` (prod) or `console` (dev) |
| `log_level_overrides` | `LOG_LEVEL_OVERRIDES` | `""` | `"name=LEVEL,name=LEVEL"`, parsed by a validator into `{logger: level}` |

**Built-in noisy-logger defaults** (applied first, then `log_level_overrides` wins) — all WARNING:
`uvicorn.access`, `sqlalchemy.engine`, `httpx`, **`asyncpg`, `temporalio`, `redis`, `alembic`** (last
four are new).

**Error handling:** invalid level names (in root or overrides) fall back to INFO but emit a
`log.invalid_level` warning so typos surface — config never crashes boot. `configure_logging` stays
idempotent (clears root handlers first).

`configure_logging(settings: LoggingSettings | None = None, *, extra_processors=None)` — reads
`LoggingSettings()` from env when not passed. `extra_processors` is the made-ready hook: a future
trace-id processor (Sentry/OTel) slots in without a rewrite. The current `create_app` / `worker.py`
call sites switch from passing `json_output`/`log_level` kwargs to constructing/relying on
`LoggingSettings` (keep a thin back-compat shim only if needed — prefer updating both call sites).

---

## 5. Processor Chain

Assembled in `config.py`. Order (shared processors, then renderer via stdlib `ProcessorFormatter`):

```
merge_contextvars
add_logger_name
add_log_level
CallsiteParameterAdder(func_name, lineno)     # commercial-grade callsite info
TimeStamper(fmt="iso", utc=True)
StackInfoRenderer
<exc-info processor>                           # format-specific (see below)
redact_sensitive                              # NEW — after exc expansion, before render
UnicodeDecoder
→ JSONRenderer (prod) | ConsoleRenderer (dev)
```

`<exc-info processor>` is chosen by output format: JSON mode uses `dict_tracebacks` (structured
traceback object); console mode uses `format_exc_info` (human-readable traceback). It is placed
**before** `redact_sensitive` so redaction also covers any sensitive values surfaced inside expanded
tracebacks.

---

## 6. Redaction — `redact_sensitive`

structlog processor `(logger, method_name, event_dict) -> event_dict`, runs immediately before the
renderer. Recurses into nested dicts and lists. For any key matching the denylist (case-insensitive,
substring), replaces the value with `"***REDACTED***"`.

**Denylist (regex, case-insensitive):**
`password|passwd|secret|token|api_key|apikey|authorization|cookie|set-cookie|access_token|refresh_token|email|service_key|jwt|bearer`

**Not redacted:** SMILES / molecule structures / chemical data (operational, not PII), UUIDs (needed for
correlation). `email` IS on the denylist (user approved; drop later if support workflows need raw emails).

---

## 7. Request Observability

### 7.1 `RequestContextMiddleware` (pure ASGI)

Pure ASGI (`async def __call__(self, scope, receive, send)`), **not** `BaseHTTPMiddleware` — avoids
its contextvar back-propagation limitation and lets us guarantee context cleanup.

Flow per request:
1. **Entry:** read `X-Request-ID` header or mint a UUID4 → `bind_request_context(request_id=...,
   http_method=..., http_path=...)`. Record start time (monotonic).
2. **Wrap `send`** to capture the response `status` and to inject the `X-Request-ID` response header.
3. **On completion:** emit one structured access log
   `request.completed { request_id, method, path, status_code, duration_ms, client_ip,
   user_id?, workspace_id? }` (user/workspace read from `scope["state"]` if auth ran — see 7.2).
4. **`finally`:** `clear_request_context()` — always, even on exception.

Only applies to HTTP scopes; passes through lifespan/websocket scopes untouched. Excludes `/health`
from access logging to avoid probe noise (still binds request_id).

### 7.2 User/workspace binding at the `get_auth` chokepoint

`get_auth` (interface/dependencies/_core.py) is the auth chokepoint — `auth.workspace_id` is referenced
383× and `auth.user_id` 56×. After auth resolves, bind both into structlog contextvars via
`bind_user_context(user_id=str(auth.user_id), workspace_id=str(auth.workspace_id))` so all post-auth
operation logs carry them, and stash them onto `request.state` (backed by `scope["state"]`) so the
middleware's access-log line can include them.

Note on the contextvar boundary: request_id is bound in the middleware *before* calling downstream, so
it propagates to every log. user/workspace are bound in the dependency (downstream); they appear on all
operation logs and — via `request.state`/`scope["state"]` — on the access-log line too.

---

## 8. Standardization Sweep

### 8.1 Logger-obtain migration (stdlib → structlog) — 7 files

All confirmed safe (none are `@workflow.defn` Temporal workflows — the two cdd orchestrators are
client-side adapter classes):

1. `application/attachment/delete_attachment.py`
2. `application/cdd_import/get_cdd_molecule_import_runtime_status.py`
3. `application/cdd_import/get_cdd_plate_import_runtime_status.py`
4. `application/chemical_registration/bulk_registration_service.py`
5. `infrastructure/persistence/unit_of_work.py`
6. `infrastructure/temporal/orchestrators/cdd_molecule_import.py`
7. `infrastructure/temporal/orchestrators/cdd_plate_import.py`

### 8.2 Call-site style fixes (`%`-format → event-name + kwargs)

- `infrastructure/temporal/worker.py` — already imports structlog, but uses `%`-style positional args
  (`"Connecting to Temporal at %s"`, `"Temporal worker started on queue %r"`). Convert to
  `logger.info("temporal.connecting", address=..., namespace=..., queue=...)` etc.
- All call sites in the 7 migrated files above.

---

## 9. Conventions (to be documented + applied)

- **Event name** = first positional arg: lowercase `snake_case`, dotted domain namespace —
  `export.skipped`, `async_job.not_found`, `request.completed`, `temporal.worker_started`. Pattern:
  `noun.verb_outcome`.
- **Data → kwargs only.** Never f-strings or `%`-formatting in the message.
- **Exceptions:** use `logger.exception("event.failed", ...)` inside `except` blocks (auto exc_info).
- **Levels:**
  - `DEBUG` — dev-only detail / verbose tracing
  - `INFO` — state transitions & business events (job started/completed, entity registered)
  - `WARNING` — recoverable / degraded (fallback taken, retryable failure)
  - `ERROR` — failed operation needing attention
  - `CRITICAL` — app-level failure

---

## 10. Testing

Unit tests using `structlog.testing.capture_logs` / a configured handler capturing stdout:

- **Redaction:** sensitive keys redacted (flat + nested dict + list-of-dict); non-sensitive keys
  (e.g. `smiles`, `molecule_id`) preserved; case-insensitive match.
- **Settings:** `LOG_LEVEL_OVERRIDES` string → dict parsing; invalid level → INFO fallback + warning;
  noisy-lib defaults applied; override beats default.
- **Middleware:** request_id minted when no header; passed through when `X-Request-ID` provided;
  `request.completed` emitted with status + duration_ms; contextvars cleared after request;
  `X-Request-ID` echoed on response; `/health` excluded from access log.
- **JSON output smoke test:** configured JSON renderer emits expected keys
  (`event`, `level`, `logger`, `timestamp`, `request_id` when bound).

All existing tests must remain green.

---

## 11. Decisions Locked

- **Tier 2** (standardize + request observability); Sentry/OTel/Prometheus made-ready, not wired.
- **Redaction included**; `email` on denylist; SMILES/chem data not redacted.
- **Backend code only** — no compose/deps/.env churn expected.
- `infrastructure/logging.py` → small package (4 files).
- structlog confirmed as the framework (already chosen); no alternative evaluated.

---

## 12. Risks & Mitigations

- **Pure-ASGI middleware correctness** (status capture, header injection): cover with middleware unit
  tests against a minimal ASGI app + a TestClient request asserting `X-Request-ID` and access log.
- **`configure_logging` signature change** could break the two call sites (`create_app`, `worker.py`):
  update both in the same change; keep a back-compat path only if a third caller surfaces.
- **Redaction false positives** (e.g. a benign key containing `token`): acceptable — fail safe toward
  redaction; denylist is centralized and easy to tune.
- **Temporal workflow determinism:** confirmed the migrated orchestrator files are client-side adapters,
  not sandboxed workflows, so structlog use is safe. (If a future workflow needs logging, use
  `temporalio.workflow.logger`, not a module logger — noted for implementers.)
