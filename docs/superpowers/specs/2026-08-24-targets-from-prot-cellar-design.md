# Targets sourced from prot-cellar — design

**Date:** 2026-08-24
**Status:** approved in chat, pending spec review
**Workspace in scope:** saclab-dev (`442df0cf-e618-4938-a089-80ae2f1e43e7`)

## 1. Problem

chem-vault2 maintains its own `targets` catalog (hand-entered, 6 rows in
saclab-dev). prot-cellar — the bio-side sibling — owns the real target catalog
(126 targets in the same Duar workspace, with organism/protein/ChEMBL linkage).
Two catalogs drift. prot-cellar becomes the **sole source of truth**; chem-vault2
mirrors it read-only.

## 2. Decisions (agreed)

| # | Decision | Rationale |
|---|----------|-----------|
| D1 | prot-cellar is the only source; chem-vault2 local target CRUD is removed | one catalog, no drift |
| D2 | Mirror rows reuse prot-cellar's target UUID as the local PK | `protocol_targets` / `run_targets` FKs, campaign target filter and `TargetRef` read models keep working untouched |
| D3 | Sync is a full scan, cursor-paged, **no cap** | prot-cellar has no `updated_after`/`ids` params; 126 rows today, paging handles growth |
| D4 | Sync is triggered from the chem-vault2 **admin UI** (new `/admin/targets` page) and best-effort on `GET /targets` when stale | admins get an explicit, error-surfacing button; chemists see new targets in pickers without asking an admin |
| D5 | Auth = forward the caller's two Duar headers | both apps are in realm `daikon-siblings`; prot-cellar accepts a chem-vault2-minted authz token as-is. No m2m, no prot-cellar changes |
| D6 | Cutover for saclab-dev: remap NadD, drop the 5 human demo targets | only NadD exists in prot-cellar; the 5 others are seed data (2 protocol links, 0 run links) |
| D7 | Mirror only `name`, `target_type`, `organism`, `chembl_id` | uniprot/gene/sequence live on prot-cellar `Protein` (one extra HTTP call per target); the row deep-links to prot-cellar instead |

## 3. Facts about prot-cellar that shape this

- `GET /api/v1/targets` — params `cursor`, `limit` (clamped 1..200, default 50), plus filters we don't use. Envelope `{items, next_cursor, total_count}`; cursor is keyset on `id`.
- DTO: `id, workspace_id, pref_name, target_type, components[{id, protein_id, relationship}], organism_id, chembl_id, chembl_url, pharmacological_class, cross_references[], version`. **No `updated_at`.** `version` is the change signal.
- `GET /api/v1/organisms/{id}` → `scientific_name` (organism names are not on the target DTO).
- Read routes call `require_editor` — a **viewer** token gets 403.
- No target DELETE endpoint → deletions never need syncing.
- Auth middleware needs both `Authorization: Bearer <IdP id_token>` and `X-Authz-Token: <Duar authz JWT>`; `svc` must equal the realm slug (`daikon-siblings`) — chem-vault2's tokens satisfy this.
- `TargetType` enum: `single_protein, domain, protein_complex, protein_family, protein_protein_interaction, nucleic_acid, organism, cell_line, tissue, unknown`. chem-vault2 lacks `domain`, `protein_protein_interaction`, `unknown`.
- Dev base URL `http://localhost:8001` (API), `http://localhost:3001` (UI). No prod deployment yet.

## 4. Architecture

### 4.1 Domain (`cellar.domain.screening_assay`)

- `Target` entity stays (it *is* the mirror row). `Target.create` / `Target.update` are replaced by a single factory `Target.from_mirror(id, workspace_id, name, target_type, organism, chembl_id)` — the id is supplied, not generated. `version` from prot-cellar is stored in a new nullable column `source_version` so unchanged rows are skipped on re-sync.
- `TargetType` gains `DOMAIN`, `PROTEIN_PROTEIN_INTERACTION`, `UNKNOWN`. Column is `String(30)` — no DB migration for the enum. One Alembic migration adds `targets.source_version INTEGER NULL`.
- `TargetRepository`: drop `count_references`; add `upsert_many(list[Target])` and `find_all_by_workspace(workspace_id)` (unpaginated, for the sync diff). `save`/`delete` stay for the cutover script.

### 4.2 Application (`cellar.application.screening`)

- **Port** `TargetSource(Protocol)` in `application/screening/target_source.py`:
  ```python
  @dataclass(frozen=True)
  class SourceTarget:
      id: uuid.UUID; name: str; target_type: str
      organism: str | None; chembl_id: str | None; version: int

  class TargetSource(Protocol):
      async def fetch_all(self, *, forwarded_headers: Mapping[str, str]) -> list[SourceTarget]: ...
  ```
  `fetch_all` pages through the cursor until `next_cursor is None`; resolves organism names via a per-call id→name cache.
- **Use case** `SyncTargetsFromProtCellar(uow, target_repo, source)`:
  - `SyncTargetsCommand(workspace_id, forwarded_headers, force: bool)`
  - `require_workspace_role(auth, "admin")` when invoked from the admin route; the best-effort path from `ListTargets` calls the same use case with `require_workspace_role(auth, "viewer")` and swallows failures (logged).
  - Diff: for each `SourceTarget`, insert if id unknown, update if `source_version` differs, skip otherwise. Rows from a *different* `workspace_id` are never touched. Returns `SyncReport(fetched, created, updated, skipped, pages)`.
  - Failure mapping: prot-cellar 401/403 → `ProtCellarAuthError` (message names the editor requirement); connection/timeout/5xx → `ProtCellarUnavailableError`. Both are `DomainError` subclasses so `result_to_response` maps them (403 / 502).
  - Freshness: an in-process `dict[workspace_id, monotonic_ts]`; `force=True` bypasses. TTL 300 s. *ponytail: per-process; Valkey if multi-replica staleness ever matters.*
  - Deletions are not synced (prot-cellar cannot delete targets). *ponytail: if prot-cellar ever adds delete, add a "missing from source" pass.*
- **Removed:** `CreateTarget`, `UpdateTarget`, `DeleteTarget` use cases.
- `ListTargets` (existing `GetTargetQuery`/`ListTargetsQuery` module) gains the best-effort refresh call before reading the mirror.

### 4.3 Infrastructure

- `infrastructure/prot_cellar/settings.py` — `ProtCellarSettings(BaseSettings, env_prefix="PROT_CELLAR_")`: `url: str = "http://localhost:8001"`, `timeout_seconds: float = 30`.
- `infrastructure/prot_cellar/target_source.py` — `HttpTargetSource(TargetSource)`: httpx `AsyncClient(transport=...)`, `GET {url}/api/v1/targets?limit=200[&cursor=…]` loop, `GET {url}/api/v1/organisms/{id}` with a per-`fetch_all` dict cache. Mirrors `OrgDirectory`'s constructor shape (base_url, transport) so tests inject a `MockTransport`.
- Persistence: `targets.source_version` column on `TargetModel`; `SqlAlchemyTargetRepository.upsert_many` via `INSERT … ON CONFLICT (id) DO UPDATE`.
- DI: `HttpTargetSourceDep` in `interface/dependencies` next to `OrgDirectoryDep`.

### 4.4 Interface (API)

- `GET /api/v1/targets` — unchanged contract; now runs the best-effort refresh first.
- `GET /api/v1/targets/{id}` — unchanged.
- **New** `POST /api/v1/targets/sync` → `SyncReportResponse{fetched, created, updated, skipped, pages}`; admin-only; forwards `Authorization` + `X-Authz-Token` from the inbound request (`request.headers`), never the service key.
- **Removed** `POST /targets`, `PATCH /targets/{id}`, `DELETE /targets/{id}`.
- `TargetResponse` is unchanged except the enum widening. Deep links to prot-cellar are built in the UI from runtime config; the backend stays URL-agnostic.

### 4.5 Frontend

- Runtime config: `frontend/src/app/api/config/route.ts` adds `protCellarUrl: process.env.APP_PROT_CELLAR_URL ?? "http://localhost:3001"` (same `APP_*` runtime pattern as `apiUrl`).
- **New page** `app/(dashboard)/admin/targets/page.tsx` → `features/screening-assay/components/admin-targets-page.tsx`: read-only targets table (name, type, organism, ChEMBL, "Open in Prot-Cellar ↗" per row) + a `SyncTargetsCard` with a **Sync from Prot-Cellar** button that calls `POST /targets/sync`, shows the returned counts, and surfaces the 403/502 messages verbatim. Added to the admin nav next to Organizations.
- `TargetList` (screening dashboard) becomes read-only and links to `/admin/targets`.
- `TargetMultiSelect`: "Create target…" → "Manage in Prot-Cellar ↗" (opens `{protCellarUrl}/targets` in a new tab). Selection semantics unchanged.
- **Removed:** `create-target-dialog.tsx`, `edit-target-dialog.tsx`, `useCreateTarget` / `useUpdateTarget` / `useDeleteTarget`, `CreateTargetInput` / `UpdateTargetInput` types. `TARGET_TYPE_LABELS` gains the three new types.
- Orval regen (`pnpm generate:api`) after the backend routes change; remove the dangling `createTargetRequest*` / `updateTargetRequest*` barrel lines by hand.

### 4.6 Cutover script (`backend/scripts/remap_targets_to_prot_cellar.py`)

One-off, run once per environment after the first admin sync:

1. Load all local targets whose `source_version IS NULL` (pre-mirror rows).
2. For each, look for a mirror row (`source_version IS NOT NULL`) with `lower(name)` equal → **remap**: `UPDATE protocol_targets / run_targets SET target_id = <mirror id>` (dedupe on the unique link constraint), then `DELETE` the old row. (Targets are not taggable — no tag links to move.)
3. No match → **drop**: delete link rows, then the target.
4. `--dry-run` (default) prints the plan; `--apply` executes in one transaction. Prints a summary table.

Expected in saclab-dev: `NadD → remapped (4 run links)`, 5 dropped (2 protocol links removed).

## 5. Error handling

| Situation | Behaviour |
|-----------|-----------|
| prot-cellar unreachable / 5xx / timeout | admin sync → 502 with message; list read → serve mirror, log `targets.sync.failed` |
| prot-cellar 401/403 (viewer token) | admin sync → 403 "prot-cellar requires editor role"; list read → serve mirror silently (viewers are expected to hit this) |
| Unknown `target_type` value from prot-cellar | map to `unknown`, log once per sync |
| Organism lookup fails for one id | `organism=None` for those rows; sync continues |
| Row exists locally with same id but different `workspace_id` | skipped, logged as `targets.sync.workspace_mismatch` (should never happen — same Duar workspace ids) |

## 6. Testing

- **Unit** (`tests/unit/application/screening/test_sync_targets.py`): create/update/skip diff by `source_version`; force vs TTL; auth error mapping; unknown type → `unknown`.
- **Integration** (`tests/integration/infrastructure/test_http_target_source.py`): httpx `MockTransport` serving 3 pages + organisms; asserts full traversal, organism cache hit count, 403 → `ProtCellarAuthError`.
- **Integration** (`tests/integration/persistence/test_target_repository_upsert.py`): `upsert_many` insert + update path, FK links survive.
- **API** (`tests/api/test_targets.py`): `POST /targets/sync` admin-only; `GET /targets` serves the mirror when the source raises; `POST/PATCH/DELETE /targets` → 405/404.
- **Frontend** (vitest): `target-multi-select.test.tsx` updated for the link; `admin-targets-page.test.tsx` renders counts after sync and the error banner on 403.
- **Script**: dry-run against a pg_dump of saclab-dev before `--apply`; verify link counts before/after.

## 7. Out of scope

- Syncing deletions (prot-cellar has no delete).
- Mirroring protein-level fields (uniprot, gene, sequence).
- Push/webhook from prot-cellar (its ADR defers cross-service events).
- Prod deployment config for prot-cellar (none exists yet); `PROT_CELLAR_URL` / `APP_PROT_CELLAR_URL` are documented in `.env.example` only.
