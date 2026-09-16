# Targets mirror (prot-cellar) — follow-ups

Non-blocking items from the final review of `feat/targets-from-prot-cellar`
(2026-08-24). Spec: `docs/superpowers/specs/2026-08-24-targets-from-prot-cellar-design.md`.

| Item | Where | Why deferred | Suggested fix |
|---|---|---|---|
| `TargetResponse` still advertises `gene_name`, `uniprot_id`, `ncbi_gene_id`, `description`, `target_class` — all permanently `null` since prot-cellar owns those on `Protein` (spec D7) | `interface/routes/targets.py`, `targets` columns | Needs a migration + DTO trim + orval regen; not required for correctness | Migration 066 drops the five columns; regenerate orval; remove from `TargetResponse` |
| `SourceTarget` drops prot-cellar's `workspace_id`; the "both apps share Duar workspace ids" assumption is load-bearing but unasserted | `infrastructure/prot_cellar/target_source.py::fetch_all` | Cannot mismatch today (realm `daikon-siblings`, same Duar workspace) | Skip-and-log rows whose `workspace_id` differs from the caller's |
| Best-effort refresh on `GET /targets` inherits the 30 s `PROT_CELLAR_TIMEOUT_SECONDS`; one lister per TTL may wait that long when prot-cellar hangs | `application/screening/sync_targets.py` (`force=False` path) | Only one request per 5-min TTL pays it (mark-on-attempt) | Shorter timeout for the best-effort path (e.g. 5 s), full timeout for admin `force=True` |
| `SyncFreshness` tests monkeypatch the global `time.monotonic` | `tests/unit/application/screening/test_sync_targets.py` | Restored by monkeypatch; fragile only under parallel test runners | Inject a clock callable into `SyncFreshness` |
| Adapter test lives under `tests/unit/infrastructure/` (spec §6 said integration) | `tests/unit/infrastructure/test_http_target_source.py` | MockTransport, no network — unit is the honest location | Update spec §6 wording or move the file |
| No unit test for the generic-`Exception` branch in the sync use case (covered end-to-end by `test_list_serves_mirror_when_source_raises_unexpected_error`) | `tests/unit/application/screening/test_sync_targets.py` | API test proves the behavior; unit duplicate is optional | Add a `FakeSource` raising `KeyError` → `Failure(ServiceUnavailableError)` |
| `btrim` name match has no whitespace-specific test | `tests/integration/scripts/test_remap_targets_to_prot_cellar.py` | Script has already run; only matters if reused on another environment | Seed `"NadD "` vs `"NadD"` and assert `remap` |
| `docker-compose.prod.yml` defaults `PROT_CELLAR_URL` to `http://localhost:8001` (inside the container that is the backend itself) | `docker-compose.prod.yml:32` | No prod prot-cellar exists yet; failure mode is a clean 503 on sync, mirror still served | Set it explicitly at deploy time (`PROT_CELLAR_URL=http://prot-cellar-backend:8001` or the `.snet` URL) |
