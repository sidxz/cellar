# `TEMPORAL_DISABLED=1` + real `create_app()` boot crashes with `lagom.exceptions.DuplicateDefinition`

**Found:** 2026-08-13, during S5 Task 10 (FE kiosk-device admin page) — needed to boot the real
backend on `:8000` for an orval regen and hit this before ever touching frontend code.

**Root cause:** `infrastructure/di/_export.py` pre-binds `ExportOrchestrator` to a
`NullExportOrchestrator` inside `create_container()` whenever `os.environ.get("TEMPORAL_DISABLED")
== "1"` (comment there: "used in tests and local dev without Temporal"). Separately,
`interface/app.py`'s `lifespan()` **unconditionally** calls
`container.define(ExportOrchestrator, Singleton(lambda: export_orch))` after its own
try/except-Temporal-connect block — regardless of whether `_export.py` already bound it. With
`TEMPORAL_DISABLED=1` set, both run, and `lagom`'s `Container.define()` raises
`DuplicateDefinition` on the second call, crashing ASGI startup
(`ERROR: Application startup failed. Exiting.`). This is **not** conditioned on Temporal actually
being unreachable — reproduced it with a real Temporal server up and connecting successfully
(`Client.connect` succeeded per `lsof` showing an ESTABLISHED connection to `:7233`), because
`_export.py`'s pre-bind only checks the env var, not whether the later connect attempt succeeds.
The `_sar_analysis.py` comment ("`NullExportOrchestrator` etc.") suggests the same
pre-bind-then-redefine pattern exists for `ScaffoldTreeOrchestrator` / `RGroupDecompositionOrchestrator`
/ `SarActivityProjectionOrchestrator` / `UmapClusterOrchestrator` / `BulkRegistrationOrchestrator` /
`CddMoleculeImportOrchestrator` — not individually confirmed (the crash on `ExportOrchestrator`,
first in the block, halts startup before the others run), but likely affected by the identical
bug once this one is fixed.

**Impact:** `TEMPORAL_DISABLED=1` + a real `create_app()` + uvicorn boot (i.e. `make dev-be` with
that env var set, or any hand-rolled boot script that copies it from
`tests/api/conftest.py` for orval regen / manual verification) cannot start at all. Backend API
tests are unaffected (they don't appear to run the full ASGI lifespan). Production/normal
`make dev-be` is unaffected today only because root `.env` doesn't set `TEMPORAL_DISABLED` and a
real Temporal server happens to be reachable — but the "local dev without Temporal" mode
`_export.py`'s own comment describes as supported is currently broken.

**Worked around (not fixed) for Task 10's regen:** booted via `make dev-be` (sources the real
root `.env` — real Sentinel URL + service key + no `TEMPORAL_DISABLED` — a real Temporal server
was already up on `:7233` in this dev environment) instead of a hand-rolled script that set
`TEMPORAL_DISABLED=1`. Out of scope for an FE task to fix backend DI wiring inline.

**Fix direction:** make `app.py`'s lifespan binding idempotent with `_export.py`'s (e.g. only
`container.define(ExportOrchestrator, ...)` when `temporal_client is not None`, since the
Null-orchestrator path is already covered by `_export.py`'s own `TEMPORAL_DISABLED` guard; mirror
for every sibling orchestrator in the same block). Verify by booting with
`TEMPORAL_DISABLED=1` and **no** Temporal server reachable at all (the actual "local dev without
Temporal" scenario the comments describe) and confirming `/openapi.json` serves successfully.
