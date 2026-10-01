# Temporal worker dispatches domain events to nobody — no audit rows for worker writes

**Found:** 2026-10-01, whole-branch review of register-to-projects.

**Symptom:** anything registered or linked inside a Temporal activity leaves no
`audit_operations` rows. Bulk registration through Temporal (the default path when
Temporal is up) emits `MoleculeRegistered`, `EntityAddedToProject`, merge events…
and every one is dropped. The same writes through the API (single registration,
bulk endpoint, the in-process sync fallback) are audited.

**Root cause:** the audit catch-all is registered only in the API lifespan —
`interface/app.py:59` `dispatcher.register(DomainEvent, AuditEventHandler(session_factory))`.
The worker (`infrastructure/temporal/worker.py:102`) takes `container[EventDispatcher]`
from the same container but never registers any handler, so `dispatch_all` is a no-op
there.

**Why it matters:** audit is append-only by design (21 CFR Part 11 alignment), and
`molecule_projects` has no `added_by`/`added_at` columns — the audit row is the only
provenance a project link has.

**Fix direction:** register the same `AuditEventHandler` on the worker's dispatcher
at startup (one shared helper used by both `app.py` and `worker.py`, so they cannot
drift again). Check what the handler reads for actor/correlation (request ContextVars)
and supply the workflow's `submitted_by` instead, then add a worker-side test that a
processed chunk writes audit rows.
