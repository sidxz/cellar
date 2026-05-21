# Cellar

Chemical compound management & screening platform (enterprise-grade). 8 bounded contexts, 17+ aggregates, 136 use cases.

**Repo:** `git@github.com:sidxz/cellar.git`
**Board:** https://github.com/users/sidxz/projects/4/views/1

---

## Stack

**Backend:** Python 3.13+ / FastAPI 0.115+ / SQLAlchemy 2.0 async (asyncpg) / PostgreSQL 16 + RDKit cartridge / Pydantic v2 / Alembic / Lagom (DI) / dry-python/returns (Railway) / Valkey 8 (Redis-compat) / Temporal / structlog / fsspec

**Frontend:** Next.js 16 / React 19 / TypeScript 5.7+ / Turbopack / shadcn/ui / Tailwind CSS v4 / AG Grid Community / TanStack Query v5 / Zustand / React Hook Form + Zod / Ketcher / RDKit.js / Tiptap / Plotly.js / orval / Playwright

**Infra:** Docker Compose / Grafana Tempo / Prometheus / Sentry (self-hosted) / GitHub Actions / ghcr.io

**Package managers:** `uv` (Python), `pnpm` (JS)

Full rationale: `docs/tech-stack.md`

---

## Architecture

DDD + Clean Architecture + Railway Pattern. No event sourcing.
Domain -> Application -> Infrastructure -> Interface layers.
Domain events for side effects (audit, notifications, async processing).
Optimistic concurrency (version column) on all aggregates.
Audit trail is append-only (21 CFR Part 11 alignment).
Auth delegated to Sentinel (external, `~/workspace/identity-service/`).

### Layer Rules

| Layer | Depends On | Never Depends On |
|-------|-----------|-----------------|
| Domain | Nothing (pure Python) | Application, Infrastructure, Interface |
| Application | Domain | Infrastructure, Interface |
| Infrastructure | Domain, Application | Interface |
| Interface | All layers | — |

### Bounded Contexts

| # | Context | Key Aggregates | Phase |
|---|---------|---------------|-------|
| 01 | Chemical Registration | Molecule, DisclosureRequest, BulkDisclosure, SynthesisRoute | 1 |
| 02 | Screening & Assay | Protocol, Run | 1 |
| 03 | Inventory | Batch, Sample, SampleRequest, Shipment, SynthesisRequest | 1 |
| 04 | SAR Analysis | MarkushDefinition, MolecularFingerprint | 2 |
| 05 | Research Organization | Project, Collection, ELNEntry, SavedSearch | 1-2 |
| 06 | Audit & Compliance | AuditOperation (append-only) | 0 |
| 07 | Workspace Config | Organization, WorkspaceSettings, ControlledVocabulary | 1 |
| 08 | Sentinel Auth | External — User, Workspace, Roles, Permissions | External |
| 11 | Formulation & Drug Product | Formulation, FormulationBatch, StabilityStudy | 2 |

---

## Project Layout

```
cellar2/
  backend/
    pyproject.toml
    alembic/
    src/cellar/
      domain/
        shared/
        chemical_registration/
        screening_assay/
        inventory/
        formulation/
        sar_analysis/
        research_organization/
        audit_compliance/
        workspace_config/
      application/
      infrastructure/
        persistence/sqlalchemy/
        rdkit/
        storage/
        messaging/
        temporal/
        di/
        sentinel/
      interface/
    tests/
      unit/ integration/ api/
    Dockerfile

  frontend/
    package.json
    next.config.ts / orval.config.ts
    components.json
    src/
      middleware.ts
      app/
        login/ auth/callback/
        (dashboard)/
      features/
        chemical-registration/
        screening-assay/
        inventory/ ...
      shared/
        components/ui/
        components/layout/
        hooks/
        lib/
        providers/
        types/
    tests/
    Dockerfile

  docker-compose.yml
  docker-compose.dev.yml
  docs/
  .github/workflows/
```

---

## Implementation Status

Phase 0-1 complete (S01-S32). Phase 2 complete (fingerprints, research org, plates, export+search). Phase 3 not started (Temporal, ELN, Markush, Formulation, observability).

Full checklist with gates: `docs/implementation-status.md`

---

## Documentation Index

> **Before writing any backend code, read `docs/backend-code-guidelines.md` and `docs/patterns-and-conventions.md`.** These contain mandatory rules for workspace scoping, auth guards, railway pattern, and a checklist for every new use case.

| Purpose | Location |
|---------|----------|
| Backend coding rules (MANDATORY) | `docs/backend-code-guidelines.md` |
| Patterns & exemplar paths (MANDATORY) | `docs/patterns-and-conventions.md` |
| Tech stack decisions + rationale | `docs/tech-stack.md` |
| Key architectural decisions | `docs/key-decisions.md` |
| Full implementation checklist | `docs/implementation-status.md` |
| Domain model (per context) | `docs/domain-model/NN-name.md` |
| Implementation plan + sessions | `docs/planning/` |
| Test scenarios & use cases | `docs/test-reference/` |
| Incomplete work items | `docs/backlog/` |
| Historical plans/specs | `docs/archive/` |

---

## Domain Model Reference

Detailed specs in `docs/domain-model/`:

| File | Content |
|------|---------|
| `00-overview.md` | Context map, cross-context relationships, attachment entity |
| `01-chemical-registration.md` | Molecule, identifiers, disclosure, merge, bulk registration |
| `02-screening-assay.md` | Protocol, runs, plates, wells, readout data, dose-response |
| `03-inventory.md` | Batches, samples, storage, requests, shipments |
| `04-sar-analysis.md` | Fingerprints, matched molecular pairs, Markush |
| `05-research-organization.md` | Projects, collections, saved searches, ELN |
| `06-audit-compliance.md` | Audit operations, entries, electronic signatures |
| `07-workspace-config.md` | Organizations, workspace settings, controlled vocabularies |
| `08-sentinel-integration.md` | Auth boundary, JWT claims, service actions |
| `09-value-objects.md` | All shared VOs (ChemicalStructure, Amount, Concentration, etc.) |
| `10-business-rules.md` | Registration rules, merge safety, chemical standards |
| `11-formulation.md` | Formulations, excipient catalog, batches, stability studies |

---

## Session Model

**Batch 3-5 related sessions per conversation.** Each conversation:
1. **Reads** this CLAUDE.md (auto-loaded) + `docs/planning/session-specs.md` for the batch
2. **Reads** `docs/patterns-and-conventions.md` + `docs/backend-code-guidelines.md` before writing code
3. **Implements** each session in order, committing after each
4. **Tests** — all tests pass before moving to next session
5. **Updates** `docs/implementation-status.md` (check off sessions)
6. **Commits + pushes** after each session
7. **Before ending** — updates "Current Session Notes" below with a brief handoff if work needs continuation

**Layer order per context:** Domain -> Domain tests -> Persistence -> Integration tests -> Application -> API -> API tests -> UI -> E2E tests

## Current Session Notes

_Per-conversation handoff. Add a brief status block when ending a session that needs continuation; keep prior handoffs out of this file once the work is shipped._

### 2026-05-21 — Configurable reg-number prefix (CV-NNNNN → CC-NNNNNN) shipped on prot-2

**Branch:** `prot-2`, +8 commits on top of the DR edit-points batch. Nothing pushed. **Browser smoke pending** (BE end-to-end smoke ran live — next reg = `CC-050668`; settings round-trip verified).

**Plan:** `docs/superpowers/plans/2026-05-21-configurable-reg-number-prefix.md` (10 tasks shipped via subagent-driven execution).

**What this is:** registration-number prefix + zero-pad width are now per-workspace settings (`registration_number_prefix` + `registration_number_width` in `workspace_settings.registration_rules` JSONB). Defaults `CC-` / `6` (1M-compound capacity). The repo's `next_registration_number` is regex-based now (`SUBSTRING ... FROM '[0-9]+$'`), tolerant of mixed prefix lengths + widths across history. Migration 042 rewrote ALL existing molecules + batches + bulk-registration items from `CV-NNNNN` to `CC-NNNNNN` (50,667 molecules — way more than the ~982 from prior handoffs, because CDD imports populated the DB).

**8 commits (oldest → newest on prot-2 after `50802aed`):**

| # | Hash | Title |
|---|---|---|
| 1 | `d3ca580b` | feat(workspace_config): per-workspace registration-number prefix + width |
| 2 | `0a5b5751` | feat(chemical_registration): regex-based reg-number lookup; signature takes prefix/width |
| 3 | `1c3b7026` | feat(chemical_registration): RegisterMolecule plumbs workspace prefix/width |
| 4 | `54bf053a` | chore(di): wire WorkspaceSettingsRepository into RegisterMolecule factory |
| 5 | `54313903` | feat(workspace_config): FE types for registration_number_prefix + width |
| 6 | `389b2137` | feat(workspace_config): UI inputs for registration_number_prefix + width |
| 7 | `be795cb5` | feat(migration): 042 — rewrite reg/batch numbers from CV-NNNNN to CC-NNNNNN |
| 8 | `88fc8b6b` | chore(frontend): update placeholders/CSV templates to CC-NNNNNN |

**Locked design decisions:**

- Identity is per-workspace (mirrors the existing `WHERE workspace_id = ?` scope of the next-number lookup). Two new keys in `registration_rules`: `registration_number_prefix` (default `"CC-"`, validated `^[A-Z]{2,8}-$`) + `registration_number_width` (default `6`, bounded `[4, 8]`).
- Counter is GLOBAL per-workspace, not per-prefix. After migration, max = 50667, next = `CC-050668`. If a workspace later switches to `MTB-`, next would be `MTB-050669`. Continuous monotonic counter avoids dedup logic complexity and prevents accidental collision.
- The lookup query uses regex `SUBSTRING(col FROM '[0-9]+$')` instead of the old `substr(col, 4)` so it tolerates any prefix length + any pad width going forward.
- `RegisterMolecule` reads settings inside the use case and passes them through; if `WorkspaceSettings` doesn't exist for a workspace (brand-new), it falls back to `WorkspaceSettings.create_default()` which surfaces the new defaults from the property getters.
- Existing data was REWRITTEN (user explicitly chose this over keep-historical), so the dev DB now has `CC-000001..CC-050667` and `CC-000001-001..` batch numbers; bulk-registration item snapshots also rewritten.
- Migration 042 downgrade has a guard that refuses to run when 5-digit projection would collide — at 50K molecules the dev DB cannot downgrade. The intended end-state is forward-only.
- `workspace_settings.registration_rules` column is typed `JSON` (not `JSONB`), so the migration uses explicit `::jsonb` casts for the `||` merge and `-` key-deletion operators. Worth noting if anyone writes a future migration on the same column.

**Important deviation from plan:** `WorkspaceSettings.update()` validation rejects `registration_number_width` being a `bool` (because `True`/`False` are int subclasses in Python). Property getter also has the `not isinstance(raw, bool)` guard. Caught during TDD on Task 1.

**Smoke checklist (pending — please run before push):**

| # | Scenario | Expected |
|---|---|---|
| 1 | Open `/settings` → Registration card | Two new inputs: "Compound Number Prefix" (CC-) + "Compound Number Width" (6) above the existing "Create batch on re-registration" switch. |
| 2 | Change prefix to `LAB-`, width to `7`, click Save | Success toast. Refresh → values persist. |
| 3 | Open compound registration wizard, register a new compound | New compound's reg number is `LAB-0000NNN` (7-digit, LAB- prefix). |
| 4 | Reset prefix to `CC-`, width to `6` | Settings save. |
| 5 | Register another new compound | Reg number is `CC-050669` (the prior LAB- one bumped the counter; new compound continues the global counter regardless of prefix change). |
| 6 | Type lowercase `cc-` in prefix field, try to save | Zod error: "Prefix must be 2–8 uppercase letters followed by a dash". |
| 7 | Try width `3` or `9` | Zod blocks (input has min/max 4/8 + Zod validation). |
| 8 | Open `/compounds/CC-000001` (lowest in DB) | Page renders normally. Aliases column shows whatever the import created. |
| 9 | Open bulk-import wizard's CSV template download | Example rows use `CC-000001` (not `CV-00001`). |
| 10 | Inventory plate-import wizard's CSV template | Example uses `CC-000001-001` for batch. |
| 11 | Compound search bar | Placeholder reads `e.g., CC-000001, Aspirin, ...`. |
| 12 | Open any existing compound page (e.g. `/compounds/CC-050667`) | Renders. Batch numbers display as `CC-050667-NNN`. |

**Diagnostic anchors:**

- `backend/src/cellar/domain/workspace_config/workspace_settings.py` — `registration_number_prefix` / `registration_number_width` properties (read from `registration_rules` JSONB with defaults `CC-` / `6`) + validation in `update()`. Single source of truth for the defaults.
- `backend/src/cellar/infrastructure/persistence/sqlalchemy/chemical_registration/molecule_repository.py::next_registration_number` — `SUBSTRING(registration_number FROM '[0-9]+$')` + `LPAD`. Robust to any prefix and width.
- `backend/src/cellar/application/chemical_registration/register_molecule.py::_resolve_reg_number_config` — single helper called from both call sites (disclosed + undisclosed branches). Falls back to `WorkspaceSettings.create_default()` if no settings row.
- `backend/alembic/versions/042_configurable_reg_prefix.py` — one-way data rewrite + workspace_settings seed. Downgrade guard refuses on collision-producing datasets.
- `frontend/src/features/workspace-config/components/workspace-settings-form.tsx` — Registration card now has prefix + width inputs with mirrored Zod validation.

**Open caveats:**

- Migration 042 downgrade cannot run on the dev DB (50K molecules → 5-digit projection collisions). This is by design — the migration is forward-only on real datasets. If we ever need to test the downgrade, it works on a database with ≤ 9999 molecules per workspace AND no projection collisions.
- The `workspace_settings.registration_rules` column is typed `JSON` (not `JSONB`) in the ORM model — any future migration touching this column needs the same `::jsonb` round-trip pattern used in 042.
- The bool-subclass guard on `registration_number_width` was added defensively because `isinstance(True, int) == True` in Python and we don't want `True` to be silently accepted as width 1 (which would also fail the `[4,8]` bound, but defensively rejected earlier).
- FE Zod has `regex(/^[A-Z]{2,8}-$/)` on the prefix input but uses CSS `textTransform: uppercase` only for display — if a user pastes lowercase, Zod blocks submission with a clear message. An onChange-uppercase transformer could be added as a follow-up if friction is reported.
- After downgrade-to-041 (not possible on this DB but hypothetically), the FE inputs would still show; they'd just read `undefined` from `registration_rules` and fall back to displayed defaults. No crash, no data corruption.

**Test totals at HEAD:**
- Backend unit suite: 2458 passed (`uv run pytest tests/unit -q`)
- Backend integration: TestNextRegistrationNumber 6/6 passed against real Postgres testcontainer
- Frontend: 534/534 passed across 64 files
- `pnpm exec tsc --noEmit`: clean

**How to resume:**

1. Walk the 12-step browser smoke checklist on the dev stack (`docker compose up -d && cd frontend && pnpm dev`).
2. If smokes pass, push `prot-2` and open a PR against `main`. This batch rides on the DR edit-points redesign batch from 2026-05-19. PR title: "DR edit-points redesign + configurable reg-number prefix (CV-→CC-)". Description should call out BOTH:
   - The DR auto-3σ behavior change (existing curves will fit differently)
   - The CV-→CC- rewrite: every compound reg number was rewritten in migration 042. Bookmarks/links using CV-NNNNN are dead. External references (CDD vault, paper notebooks) referencing CV-NNNNN won't auto-resolve. Chemists should be informed of the new identifier scheme.
3. After deploy: existing chemists need to be informed of the CV-→CC- rename. CV-00001 → CC-000001, CV-00982 → CC-000982, etc. The numeric tail is preserved exactly.

### 2026-05-19 — DR edit-points redesign (Sprints 1+2+3) shipped on prot-2

**Branch:** `prot-2`, 28 new commits since `bcdaf070`. Nothing pushed. **Browser smoke pending.** BE 2440/2440 unit pass; FE 534/534 across 64 files; `pnpm exec tsc --noEmit` clean.

**Plan:** `docs/superpowers/plans/2026-05-19-dr-edit-points-redesign.md` (22 tasks shipped via subagent-driven execution with two-stage review per task + a final integration review).

**What this batch is:** chemist reported the DR-curve "Edit Points" UX is broken — clicking one point silently eliminates more (cascade), counter says "10/10" even with X markers on screen, no save/cancel/undo. Investigation confirmed three FE/BE bugs + an entire missing edit-session model. Redesigned end-to-end: explicit edit session with draft state, preview-refit endpoint (compute-only), commit-refit with audit trail, auto-3σ becomes suggestion (no more cascade), side-panel inventory, save dialog with reason field, edit history popover, locked-curve guard, keyboard shortcuts.

**Big behavioral change to flag for the user:** Auto-3σ outlier detection NO LONGER silently excludes points. From now on every newly-imported run will include all captured points in the fit, with yellow-halo "suggested for exclusion" markers on outliers. Chemists explicitly accept or reject. This is industry alignment (CDD, Prism, Genedata) and the right behavior under 21 CFR Part 11, but: **chemists who knew the old fits will now see different fitted_value / r_squared / top / bottom on the same data**. PR description should call this out.

**Locked design decisions** (in the plan file):
- Refit-preview is server-side (parity with commit refit; 50ms latency acceptable).
- Exclusion reasons: hardcoded enum for V1 — `outlier`, `instrument_artifact`, `concentration_error`, `contamination`, `qc_failure`, `other`. ControlledVocabulary integration deferred.
- Approved/locked curves: edit mode disabled with "Unapprove run to edit" banner. Curve versioning deferred.
- Auto-3σ: emitted as suggestions, never silently excluded.
- Schema: enriched the existing `excluded_points` JSONB shape; no new column. Legacy entries backfilled as `source=auto_3sigma, excluded=true` with `idx=null`.
- Side panel: split-pane desktop. Drawer on narrow screens (V1 uses fixed widths).
- Audit op type: new `OperationType.CURVE_POINT_EXCLUSION`.

**28 commits (oldest → newest):** `2efe6242 · 995d078a · 373b6852 · d2285552 · 0c795e48 · a54b525f · 31a75484 · ae2c2753 · 7d327ae7 · 99f277fb · b697058f · 1d5dfdfe · 833554ba · e4126a91 · 37151f53 · 9d7a349d · 111fed91 · c98e6262 · e2a32025 · 8c0c98e7 · e03a1e48 · 0c44539c · 7a4b0221 · f42176c8 · b975038f · 748709df · 3f040d42 · 1862226e`. See `git log bcdaf070..HEAD --oneline` for titles.

**Critical post-deploy step — RUN BEFORE CHEMISTS USE THE NEW UI:**

The bulk-refit script `backend/scripts/refit_all_dose_response.py` MUST be re-run after migration 041 lands on each environment. Without it:
- Existing curves keep their legacy excluded_points shape (post-041 backfilled, but with idx=null AND no auto-3σ suggestions because Task 2.7's behavior change only fires on new fits).
- Chemists opening an old curve will NOT see yellow-halo suggestions.

The script reads each curve's raw_data + excluded_points, reconstructs the merged set, runs the new fitter (which emits suggestions instead of silently excluding), writes back. Curves with strong outliers will show LOWER R² + shifted EC50 — the outliers are back in the fit. The old "clean" fits were hiding silent data manipulation. After that, also rerun `backend/scripts/rebuild_campaign_curve_snapshots.py --include-closed` (campaign snapshots derived from those curves are stale).

**Top-priority smoke checklist before push:**

| # | Scenario | Expected |
|---|---|---|
| 1 | Open a DR run with auto-excluded points pre-deploy → hard-reload | Counter reads "N of M" honestly (e.g. "8 of 10"), NOT "10/10" |
| 2 | Edit Points → click one included point | Only that one point gains an X marker. Refresh; no new auto-exclusions appeared |
| 3 | Edit Points → click a point → Save → dialog → pick reason + note → Save | Curve updates. `SELECT * FROM audit_operations WHERE operation_type='curve_point_exclusion' ORDER BY started_at DESC LIMIT 3;` shows the event |
| 4 | In edit mode, click points | Dashed indigo "preview fit" line updates (debounced ~300ms) |
| 5 | Open a curve where the run-import detected an auto-3σ outlier | Amber `circle-open` halo, NOT an X marker |
| 6 | Click "History" button next to "Edit Points" | Popover shows prior saves with relative timestamps + reasons |
| 7 | Approve a run → open one of its curves | "Edit Points" disabled, "Locked" badge visible |
| 8 | Edit mode: Cmd+Z / Cmd+Shift+Z / Esc (dirty / clean) | Undo, redo, confirm-then-exit / exit |
| 9 | Save with one manual exclusion → re-open → click another point | BE excludes the point you actually clicked (final integration review caught this; commit `1862226e` fixed it) |
| 10 | Open a curve that existed pre-migration | Legacy X markers still render. "Legacy exclusions (read-only)" section in side panel lists them |

**Diagnostic anchors:**

- `backend/src/cellar/application/screening/_dr_point_reconstruction.py` — single source of truth for "merge raw_data + excluded_points, sort by concentration, mark excluded indices." The FE's `capturedPoints` memo in `dose-response-chart.tsx` MUST mirror this exactly.
- `backend/src/cellar/application/screening/refit_dose_response.py:268` — Sprint 2 vs Sprint 1 branch in commit refit. `exclusions` provided → audit + outlier_sigma=None + auth required. Bare `excluded_indices` → Sprint 1 contract.
- `backend/src/cellar/infrastructure/lmfit/curve_fitter.py:241-285` — auto-3σ suggestion emission (no cascade). `outlier_sigma=None` short-circuits suggestions.
- `backend/src/cellar/domain/screening_assay/excluded_point_detail.py` — domain VO + `to_jsonb`/`from_jsonb`. Match the FE `DraftExclusion` shape field-for-field.
- `frontend/src/features/screening-assay/components/dose-response-chart.tsx::capturedPoints` (~line 480) — merged-sorted captured set. ALL click indexing goes through this.
- `frontend/src/features/screening-assay/hooks/use-edit-session.ts` — draft state machine. Re-seeds on curveId change; preserves edits across parent re-renders within the same curve.
- `frontend/src/features/screening-assay/hooks/use-refit-preview.ts` — debounced (300ms) preview call. Cancels in-flight via AbortController. Preserves prior `data` on error.

**Open caveats (deferred, not blockers):**

- `compound_curves_reader.py` still returns raw dicts for `excluded_points` (intentional — reader's wire shape IS the on-disk JSONB shape). Consumers should treat as JSON.
- Multi-curve editing on the run-page comparison view is single-curve-only in V1. Chart's edit mode operates on `curves[0]`.
- Radix `DialogContent` a11y warning ("Missing 'Description'") fires from `SaveExclusionsDialog` + sibling dialogs — pre-existing pattern in this codebase.
- `useEditSession` sources `authorId` from `useAuthz()` in `@sentinel-auth/nextjs`. BE re-stamps `author_id` from `auth.user_id` server-side, so FE value is advisory.
- Pre-existing FE working-tree files `frontend/src/features/research-organization/components/search/results-grid.tsx` and `frontend/src/shared/components/data-grid/data-grid.tsx` remain modified-but-unstaged from before this session — never touched by this batch.

**How to resume:**

1. **DB migrations:** `cd backend && uv run alembic upgrade head` (only migration 041 is new; idempotent on dev where applied).
2. **Bulk refit:** `cd backend && uv run python scripts/refit_all_dose_response.py` then `uv run python scripts/rebuild_campaign_curve_snapshots.py --include-closed`.
3. **Browser smoke:** walk the 10-step checklist above on the dev stack.
4. **Push + PR:** if all smokes pass, push `prot-2`, open a PR against `main`. This batch rides on top of un-pushed V1/V1.5/V2 collections + scaffold-tree work. Title: "DR edit-points redesign (Sprints 1+2+3)". Description should call out the auto-3σ behavior change + the bulk-refit prerequisite.
5. **V3 (UMAP cluster map) next:** brainstorm in a fresh conversation per the prior session's resume plan.

---

### 2026-05-18 — Roadmap: V1 ✓ · V2 ✓ (push pending) · V3 next · V4 deferred

| | Phase | Status |
|---|---|---|
| **V1** | Collections UX redesign (cards default, virtualized grid, header strip) | shipped, awaiting push |
| **V2** | Bemis-Murcko scaffold tree on `/collections/{id}?view=tree` + scaffold filter on `/search` + ergonomic loop closer | shipped, awaiting push |
| **V3** | UMAP cluster map + activity heatmap; lasso → save-as-collection | **next — unstarted** |
| **V4** | Scale-at-10K: per-scaffold fetch + server-side scaffold-membership filter | deferred; triggers when first collection > 10K mols. Spec: `docs/superpowers/specs/2026-05-17-scaffold-tree-v4-at-scale.md` |

**Branch:** `prot-2`, ~57 commits ahead of origin. Eight unpushed sessions: V1 + V1.5, V2 base, V2 post-smoke, multi-run aggregation, unified export, DR display honesty, scaffold-tree polish, **this session = V2 closing polish**. All tests green; `pnpm exec tsc --noEmit` clean.

**This session (V2 closing polish):** Waves 0/1/4 of `docs/superpowers/specs/2026-05-17-followup-batch-design.md` + one real bug fix. Commits `2e3be354..HEAD` — see `git log` rather than rehashing here. The bug fix worth highlighting: commit `4d0161f4` split saved-search + scaffold handoffs into prepare-then-fire effects, killing the recurring "page sticks in skeleton on soft nav" bug (root cause was a single mount-time effect capturing a stale TanStack Query observer; mutate returned silently without firing the network request). This is a class-of-bug fix — should resolve similar reports across earlier prior handoffs too.

**Top-priority smoke before push (verifies the class-of-bug fix):**
1. Soft-nav scaffold loop closer: click scaffold icon from a tree node → land on `/search` with results, NOT skeleton-stuck.
2. Soft-nav saved-search: click a saved search from the list → auto-executes, NOT skeleton-stuck.

Lower-priority smokes (Ketcher drawer + preview, Groups-mode loop closer parity, Sonner toast on > 500-mol collection, frozen-collection state) are listed in the spec's acceptance criteria.

**V3 next session:** UMAP-on-Morgan-FP via Temporal workflow + `POST /api/v1/embeddings/umap` (BE). `ClusterMapView` (Plotly scatter, lasso → save-as-new-collection) + `HeatmapView` (AG Grid cellStyle) (FE). Brainstorm first — V3 has chemistry decisions (fingerprint choice, embedding dimensions, cluster algorithm) and UX decisions (lasso interaction, heatmap pivot axes) that need chemist alignment before code.

**Carry-overs that stay deferred** (don't accumulate more V2 polish — push V2 + move to V3):
- `SearchQueryBuilder` is dead code (zero production callers). Cleanup PR welcome.
- Wave 5 (lift `/search` ResultsGrid into ResultsSurface) — biggest piece in the deferred plan; defer past V3.
- color-by-protocol on `/collections` scaffold tree (activityData threading); scaffold chip on MoleculeCard; Valkey cache layer swap; precompute scaffold trees on collection-membership change.

**Resume:** smoke top-2 → push `prot-2` → open PR with all 8 sessions' work → start V3 brainstorm in a fresh conversation.

---

### 2026-05-17 — V2 scaffold tree: post-smoke polish + chemistry correctness + scale fixes

**Branch:** `prot-2`. 11 commits on top of the V2 base ship (`9436e1ed`). Nothing pushed — branch is now **41 commits ahead of `origin/prot-2`**. **Browser smoke pending** on the most-recent fixes (smoke checklist below).

**Spec for V4 deferrals:** `docs/superpowers/specs/2026-05-17-scaffold-tree-v4-at-scale.md` (per-scaffold-fetch + server-side scaffold-membership filtering, triggered on first collection > 10K mols).

**What this batch is:** chemist-driven correctness + UX iteration after the V2 ship. Started with the chemist saying "the layout is broken" → ended with the tree rendering correct Bemis-Murcko scaffolds, proper Schuffenhauer parent/child semantics, two sub-modes (Groups default + Hierarchy opt-in), and full-collection compute that bypasses the search-pagination clamp.

**Commits (oldest → newest):**

| # | Hash | Title |
|---|---|---|
| 1 | `be812e20` | fix: backfill script must eagerly import sibling model modules (FK resolution) |
| 2 | `b01aed5a` | fix: split-pane layout — string sizes (percent) + explicit height (v4 API change) |
| 3 | `30307a21` | fix: drop SMILES text + bump thumbnail to 80px (chemists read structures) |
| 4 | `884cffd1` | perf: hoist + memoize O(N²) tree work into the parent (dev-server memory) |
| 5 | `a1b59a08` | fix: emit clean ring-only scaffolds, parent=simpler |
| 6 | `f799c2ec` | feat: Path A — frequency sort + hide phantom roots + min-mols filter |
| 7 | `4ed64398` | feat: Path B — Groups sub-mode (default) + Hierarchy toggle |
| 8 | `c099c641` | fix: see the FULL collection, not just the visible page (BE collection_id input) |
| 9 | `300f4fc5` | fix: relax pagination cap for {type:'collection'} queries |
| 10 | `550e56ee` | docs: CLAUDE.md handoff + V4 deferral spec (this entry) |
| 11 | `f4640aa6` | feat: name the view-mode toggle (List|Grid|Scaffold) + clearer color picker |

**Locked design decisions from this session:**

- **`react-resizable-panels` v4 uses STRING sizes for percentages, NUMBER for pixels.** Saved as `feedback_react_resizable_panels_v4_pixels.md`. Bit us once; flagged for permanence.
- **Tree node = 80px structure thumbnail only, no SMILES text.** Chemists read structures not strings; the long font-mono SMILES label was visual noise.
- **`rdScaffoldNetwork.ScaffoldNetworkParams()` defaults emit 4 variants per scaffold** including a `*`-marked "with attachments" form and the full-decoration molecule itself. We disable everything except `includeScaffoldsWithoutAttachments`, AND feed the stored Bemis-Murcko scaffolds (not full mols) as input. Result: every emitted node is a ring-only skeleton.
- **Edge tuple convention: `(parent_simpler, child_more_complex)`** — chemist-intuitive. RDKit's native `(beginIdx, endIdx)` is `(complex, simpler-ancestor)`; we flip on the way out.
- **`MAX_PAGE_SIZE = 200` is a SEARCH-endpoint cap, wrong for collection fetches.** New `COLLECTION_FETCH_MAX_PAGE_SIZE = 10_000` applies when the search body is a single `{type:"collection"}` criterion. The chemist who opens `/collections/{id}` expects every member; pagination is wrong UX.
- **Two-mode toggle inside the tree view: Groups (default) | Hierarchy.** Groups = flat freq-sorted distinct Murckos (the chemist's typical first scan). Hierarchy = Schuffenhauer DAG (SAR drill). Path A's improvements apply to Hierarchy; Groups is inherently flat + sorted.
- **Min-mols pill cycles 1 → 2 → 3 → 5 → 10.** In Groups: hides chemotypes below threshold. In Hierarchy: prunes any subtree below threshold (recursive via `visibleNodes` Set).

**Surfaces touched (FE):**
- `frontend/src/features/sar-analysis/components/scaffold-tree-view.tsx` — split-pane, sub-mode dispatch, toolbar (sub-mode + min-mols + color), uses `collectionId` when on a collection page
- `frontend/src/features/sar-analysis/components/scaffold-tree-node.tsx` — single recursive node row; receives precomputed `childIndex` + `colorBins` + `visibleNodes` (O(N) not O(N²))
- `frontend/src/features/sar-analysis/components/scaffold-groups-list.tsx` — NEW: flat frequency-sorted list (Groups mode)
- `frontend/src/features/sar-analysis/components/scaffold-color-picker.tsx` — protocol picker for tree-node coloring
- `frontend/src/features/sar-analysis/lib/use-tree-sub-mode.ts` — NEW: URL state hook (`?sub=hierarchy` is opt-in; default is implicit groups)
- `frontend/src/features/sar-analysis/hooks/use-scaffold-tree.ts` — accepts EITHER `collectionId` (preferred when available, server-side expansion) OR `moleculeIds` (ad-hoc)
- `frontend/src/features/research-organization/components/collection-detail.tsx` — passes `collection.id` through ResultsSurface so the tree gets full membership
- `frontend/src/features/research-organization/components/results/results-surface.tsx` — adds optional `collectionId` prop, threads it to ScaffoldTreeView
- `frontend/src/features/research-organization/hooks/use-collection-search.ts` — default `limit` 1000 → 10000 (matches the new BE cap for collection queries)

**Surfaces touched (BE):**
- `backend/src/cellar/infrastructure/rdkit/scaffold_network_builder.py` — explicit ScaffoldNetworkParams (only `includeScaffoldsWithoutAttachments=True`), edge tuple flipped
- `backend/src/cellar/application/sar_analysis/build_scaffold_network.py` — feeds stored Bemis-Murcko scaffolds (not full mols), deduplicated
- `backend/src/cellar/interface/routes/scaffold_tree.py` — accepts `collection_id` XOR `molecule_ids`; expands collection server-side via `ListCollectionMolecules` (limit 100K)
- `backend/src/cellar/interface/routes/search.py` — `_is_single_collection_query` detector + per-call `cap` parameter to `clamp_limit`
- `backend/src/cellar/application/shared/pagination.py` — `clamp_limit(limit, *, max_size=MAX_PAGE_SIZE)` accepts override; adds `COLLECTION_FETCH_MAX_PAGE_SIZE = 10_000`
- `backend/scripts/backfill_bemis_murcko.py` — eager imports of cross-context model modules (FK resolution fix)

**V4 deferred items (see `docs/superpowers/specs/2026-05-17-scaffold-tree-v4-at-scale.md`):**
- Path A: server-side scaffold-membership filtering (B-tree index on `bemis_murcko_smiles` + `find_by_scaffold` endpoint). Triggers: collection > 10K mols, or chemist reports count mismatch.
- Path B: per-scaffold lazy fetch by IDs on click. Pairs naturally with virtualized "show all" pane on huge collections.
- Don't build either preemptively — current usage lives well under 10K.

**Smoke checklist (please run before push):**

| # | Scenario | Expected |
|---|---|---|
| 1 | Restart `pnpm dev` (clear bloated HMR cache from earlier sessions) | Server boots, no "memory threshold" warning |
| 2 | Open `Lead Series A - Quinazolines` (5 mols) → `?view=tree` | Groups mode default; ~3-5 chemotypes shown sorted by count desc; chevrons gone; bold count badges |
| 3 | Click a chemotype | Cards filter to its direct members only |
| 4 | Toggle to Hierarchy | Schuffenhauer DAG; top-3 roots auto-expanded; phantom-parent rows hidden; subtree counts ascend |
| 5 | Pop the Min pill to 2 | Singleton chemotypes hide; empty-state shows "back to Min=1" link if all filtered |
| 6 | Open the 900-mol `large` collection in tree view | "Computing scaffold tree…" caption ~10-30s on first load; ready state shows ALL chemotypes; "no scaffold" bucket shows 33 mols |
| 7 | Click "no scaffold" | RIGHT pane shows 33 cards (Ca²⁺, Fe³⁺, peptides, fatty acids), not 9 |
| 8 | Refresh the same collection | <500 ms response (cache hit on `ids_hash`) |
| 9 | Switch to a protocol in the color-by dropdown | Tree nodes shade (color bands appear where data exists); refresh doesn't reset |
| 10 | Visit `?view=tree&sub=hierarchy` (deep link) | Lands in Hierarchy mode on first paint |
| 11 | View-mode toggle top-right | Shows three labeled segments: `List`, `Grid`, `Scaffold` (icon + text, labels hide on narrow screens) |
| 12 | Open the 900-mol `large` collection in tree view (no protocol activity) | `Color by:` picker is HIDDEN entirely (no dead control) |
| 13 | Open a collection with protocol activity (Mtb_WCA mols) in tree view | `Color by:` prefix label visible; dropdown shows "none" + actual protocol names |

**Diagnostic anchors (post-iteration):**
- Scaffold cleanliness comes from `ScaffoldNetworkParams` with `includeScaffoldsWithAttachments=False` AND from feeding stored Bemis-Murcko scaffolds as input (not full mols).
- Edge `parent_smiles` is the SIMPLER ancestor (chemist-intuitive). Codebase-internal RDKit emit is the opposite; flip happens in `ScaffoldNetworkBuilder.build()`.
- Full-collection compute uses the BE `collection_id` expansion path (`POST /scaffold-tree` with `collection_id`); the FE detects via the `collectionId` prop on `ScaffoldTreeView`.
- `useCollectionSearch` now defaults to `limit=10000`; the BE search route detects `{type:"collection"}` single-criterion bodies and applies `COLLECTION_FETCH_MAX_PAGE_SIZE` to honor it.

**Test totals:** 197 FE tests in scope (research-org + sar-analysis); 20 BE scaffold-tree unit + 5 API tests; 2611+ BE total. All green.

**How to resume:**
1. Walk the 10-step smoke checklist above on the live dev stack.
2. If all pass: push `prot-2` and open a PR against `main`. This batch rides along with the prior V2 base ship + Collections V1 + V1.5.
3. Stale-cache cleanup: `DELETE FROM scaffold_tree_jobs WHERE status='ready';` runs cleanly between deployments to invalidate any pre-fix cached jobs.

---

### 2026-05-17 — V2 scaffold tree shipped on prot-2 (28 commits, all tests green)

**Branch:** `prot-2`. 28 new implementation commits + 3 spec/plan commits since the prior session's HEAD (`7837b3a4`). Total now ~78 commits ahead of `origin/prot-2`. **Browser smoke pending.**

**Spec:** `docs/superpowers/specs/2026-05-17-scaffold-tree-v2-design.md`. **Plan:** `docs/superpowers/plans/2026-05-17-scaffold-tree-v2.md` — 28 TDD tasks shipped via subagent-driven execution with two-stage review.

**Behavior change:** `/collections/{id}` and `/search` get a new opt-in **scaffold-tree view-mode** (toggle in the view-mode segmented control, URL `?view=tree`). Default stays `cards`. Renders a Bemis-Murcko scaffold network (left pane, recursive tree, picks a protocol from the result-set's activity to color nodes) + the existing `CardGrid` (right pane, filtered to the selected node's subtree).

Per-molecule `bemis_murcko_smiles` is now computed at registration (mirrors the fingerprint pattern). A one-shot `backfill_bemis_murcko.py` script populates legacy rows. The endpoint is sync-with-cache for ≤500 mols, async via Temporal for larger sets. Postgres-as-cache via `scaffold_tree_jobs.result_json` JSONB + a partial index on `(ids_hash, completed_at DESC) WHERE status='ready'` (Valkey deferred — wire it when another feature needs it).

**Commits shipped** (oldest → newest, all on prot-2):

| # | Hash | Title |
|---|---|---|
| 1 | `0446c31e` | migration 037 — bemis_murcko_smiles on molecules |
| 2 | `58e3ddfb` | Molecule.bemis_murcko_smiles field |
| 3 | `21bfcfb7` | MoleculeModel bemis_murcko_smiles + repo round-trip |
| 4 | `5e64ad18` | MurckoScaffoldCalculator infra wrapper |
| 5 | `72d051dd` | StructureProcessor emits bemis_murcko_smiles |
| 6 | `255e9174` | RegisterMolecule writes bemis_murcko_smiles |
| 7 | `d7c79f3a` | one-shot backfill_bemis_murcko script |
| 8 | `1179233b` | migration 038 — scaffold_tree_jobs (table + cache index) |
| 9 | `a731a0c3` | domain types — ScaffoldTreeNode/Edge/Result/Stats |
| 10 | `1a398a6a` | ScaffoldTreeJob aggregate + state machine |
| 11 | `f2673553` | ScaffoldTreeJobRepository with cache lookup |
| 12 | `c37c74c5` | ScaffoldNetworkBuilder infra wrapper |
| 13 | `e15072b7` | BuildScaffoldNetwork use case (cache-aware, NO_SCAFFOLD bucket) |
| 14 | `23b14829` | StartScaffoldTreeJob — sync/async dispatch |
| 15 | `4534976d` | Temporal workflow + activity + orchestrators |
| 16 | `ee96d85f` | GetScaffoldTreeJob + CancelScaffoldTreeJob use cases |
| 17 | `0de611ee` | DI wiring for sar_analysis context |
| 18 | `f43a453e` | POST /scaffold-tree + GET/cancel job endpoints |
| 19 | `7a1f7ac7` | regenerate orval client for /scaffold-tree endpoints |
| 20 | `4367898e` | chore(deps): add shadcn Resizable for split-pane |
| 21 | `4b5c9ce5` | FE wire types + NO_SCAFFOLD sentinel |
| 22 | `da835fab` | scaffold-tree-math — subtree + child-index helpers |
| 23 | `832e28bc` | scaffold-rollup — median pIC50 + 4-bin classification |
| 24 | `bec96c8e` | useScaffoldTree — sync return + async poll |
| 25 | `c2aff11f` | ScaffoldColorPicker dropdown |
| 26 | `e47065ee` | recursive ScaffoldTreeNode component |
| 27 | `30da1513` | ScaffoldTreeView split-pane composition |
| 28 | `6922944a` | wire scaffold-tree view-mode into ResultsSurface + toggle |

**New bounded context: `sar_analysis`.** First members landed: `domain/sar_analysis/{scaffold_tree_job,scaffold_tree_types}.py`, `application/sar_analysis/{build_scaffold_network,start_scaffold_tree_job,get_scaffold_tree_job,cancel_scaffold_tree_job,run_scaffold_tree,repositories}.py`, `infrastructure/persistence/sqlalchemy/sar_analysis/`, `infrastructure/di/_sar_analysis.py`, `infrastructure/temporal/{workflows,activities,orchestrators}/scaffold_tree.py`, `interface/routes/scaffold_tree.py`. FE: `features/sar-analysis/{types,lib,hooks,components}/`.

**Cache design (locked).** `scaffold_tree_jobs` table doubles as the cache — `find_cached(ids_hash, ttl_seconds=3600)` joins on `ids_hash + status='ready' + completed_at > NOW() - 1h` (served by the `scaffold_tree_jobs_cache` partial index). Sync path persists a READY job so the next call hits the cache. Async path mirrors the export-job pipeline shape exactly (NullOrchestrator for `TEMPORAL_DISABLED=1`, TemporalOrchestrator otherwise).

**Dispatch logic.** `POST /api/v1/scaffold-tree`:
- 200 with `{tree, job: null}` on cache hit OR set size ≤ 500
- 202 with `{tree: null, job: {...}}` on cache miss + > 500
- `GET /api/v1/scaffold-tree/jobs/{id}` polls (status + tree if ready)
- `POST /api/v1/scaffold-tree/jobs/{id}/cancel` cancels (idempotent on terminal)

**Activity rollup is FE-side.** The BE payload is pure-structural (nodes/edges/counts). `<ScaffoldColorPicker>` picks a protocol from the result-set's `activityData`; `scaffold-rollup.ts::medianPic50ForMols` rolls up node coloring. Locked default: **no color** (chemist opts in to a protocol). ND-qualified and non-positive values excluded.

**Smoke checklist (pending — please run before push):**

| # | Scenario | Expected |
|---|---|---|
| 1 | `uv run alembic upgrade head` on dev DB | Migrations 037 + 038 land cleanly |
| 2 | Register a new molecule via UI | `select bemis_murcko_smiles from molecules where id = ?;` returns canonical SMILES (or `""` for acyclic) |
| 3 | `uv run python backend/scripts/backfill_bemis_murcko.py --batch-size 500` | Logs `backfill_batch_done` per batch; second run reports 0 processed |
| 4 | Open `/collections/{id}` with ≥ 10 ringed mols, hard-reload | View-mode toggle shows three segments; default is `cards`; no scaffold UI visible |
| 5 | Click the third segment (Tree view) | URL gains `?view=tree`; left pane shows tree (first-level roots auto-expanded); right pane shows ALL mols via CardGrid |
| 6 | Click an inner scaffold node | Right pane filters to subtree members (count matches `subtree_molecule_count`); ChevronDown rotates |
| 7 | Click a leaf node | Right pane shows that node's mol(s) only |
| 8 | Click the selected node again | Deselect — right pane returns to all mols |
| 9 | Pick a protocol from the color-by dropdown | Tree nodes gain colored bars on the right (red→amber→orange→emerald for activity bins); nodes with no data show no band |
| 10 | Switch protocols in the dropdown | Bands re-color immediately; no "Computing…" flash |
| 11 | Open a > 500-mol collection in tree view | "Computing scaffold tree…" caption appears; tree renders within ~30s; second open is instant (cache hit on `ids_hash`) |
| 12 | `select status, ids_hash, completed_at from scaffold_tree_jobs order by requested_at desc limit 5;` | Recent ready jobs visible; `result_json` populated |
| 13 | Add a mol to the collection, re-open tree view | New `ids_hash` → cache miss → recompute |
| 14 | Open a collection of only acyclic compounds (CCCCC etc.) | Tree shows ONE node: "no scaffold" (italic). Right pane has all mols. |
| 15 | Drag the resizable divider | Left pane resizes between min 20% and max 50% |
| 16 | Switch back to `cards` view | URL drops `?view=`; CardGrid renders intact |

**Diagnostic anchors:**
- `frontend/src/features/sar-analysis/components/scaffold-tree-view.tsx::ScaffoldTreeView` — split-pane composition; calls `useScaffoldTree({moleculeIds})` and filters CardGrid via `collectSubtreeMolIds`.
- `frontend/src/features/sar-analysis/hooks/use-scaffold-tree.ts::useScaffoldTree` — single source of truth for sync vs async path; mocks via `startFn` / `pollFn` overrides for tests.
- `backend/src/cellar/application/sar_analysis/start_scaffold_tree_job.py::StartScaffoldTreeJob` — sync-or-async dispatch. Sync path always persists a READY job so the next call cache-hits.
- `backend/src/cellar/application/sar_analysis/build_scaffold_network.py::BuildScaffoldNetwork` — pipeline. Membership comes from stored `bemis_murcko_smiles` (NOT re-derived); hierarchy from `rdScaffoldNetwork.CreateScaffoldNetwork`.
- `backend/src/cellar/infrastructure/persistence/sqlalchemy/sar_analysis/scaffold_tree_job_repository.py::SQLAlchemyScaffoldTreeJobRepository.find_cached` — Postgres cache lookup; partial index `scaffold_tree_jobs_cache` serves it.
- `backend/src/cellar/infrastructure/temporal/workflows/scaffold_tree.py` + `activities/scaffold_tree.py` + `orchestrators/scaffold_tree.py` — mirrors export pipeline exactly. `TemporalScaffoldTreeOrchestrator` bound in `app.py` lifespan (not in DI directly).

**Open caveats / known gaps:**
- **`ResultsSurface` doesn't currently pass `activityData` to `<ScaffoldTreeView />` from `collection-detail.tsx`** — the collection search endpoint doesn't return activity columns, so color-by-protocol will render the dropdown with NO options (until activity data is threaded). The tree itself works; color-by is a follow-up. Easiest fix: extend `useCollectionSearch` to optionally fetch activity for the page-visible mols (mirroring the search-grid path).
- Tree-pane default 30%; min 20% max 50%. Tunable post-smoke if it crowds on standard laptop screens.
- Sonner "Computing scaffold tree…" toast at 3s NOT implemented (deferred — inline caption suffices for V2 MVP per spec follow-ups).
- The Docker temporal-worker container is broken (`No module named 'cellar'` from a pre-existing `uv sync --no-install-project` issue in `backend/Dockerfile`) — local `uv run` works fine. Pre-existing, not caused by this work.
- Pre-existing failures in `tests/api/molecules/test_test_counts.py` (missing `visibility` column in fixtures) — NOT caused by this work; flagged by the Task 18 implementer.

**How to resume:**
1. Spin dev stack: `docker compose up -d && cd frontend && pnpm dev`. Confirm Temporal worker is reachable (locally via `uv run python -m cellar.infrastructure.temporal.worker` since the Docker image is broken).
2. `cd backend && uv run alembic upgrade head` — migrations 037 + 038 should apply cleanly.
3. `cd backend && uv run python scripts/backfill_bemis_murcko.py --batch-size 500` — backfill legacy rows.
4. Walk the 16-row smoke checklist above on at least one ringed-mol collection AND one acyclic-only collection.
5. If smokes pass, push `prot-2` and open a PR against `main`. PR scope: "V2 scaffold tree" — also rides along the un-pushed V1/V1.5 collections work from the prior session.
6. If color-by-protocol stays empty on smoke #9, decide: ship V2 without coloring + log a follow-up to thread `activityData` through `CollectionDetail → ResultsSurface → ScaffoldTreeView`, OR block the merge on that thread.

**Follow-ups (deferred from spec):**
- Thread `activityData` from `CollectionDetail` → `ResultsSurface` → `ScaffoldTreeView` (so color-by-protocol actually has data).
- Sonner toast upgrade after 3s of async computing (with Cancel action).
- Precompute scaffold trees on collection-membership change (Temporal event handler) — fixes the "first chemist on a 10K collection waits 60s" tax.
- Scaffold filter row in `SearchQueryBuilder` ("compounds with scaffold X").
- Scaffold chip on `MoleculeCard` (subject to V1.5 card-density rule).
- Move cache layer to Valkey once another feature needs it.
- Hoist view-mode toggle + scaffold tree onto standalone `/search`.

---

### 2026-05-17 — Collections V1 + V1.5 shipped on prot-2

**Branch:** `prot-2`. 15 commits since the prior session HEAD (`88b43fcb`). Nothing pushed. **Browser smoke pending** (V1.5 smoke walks the protocol-test-count line, frozen chip, provenance link, single-row strip). BE unit tests pass (+4 new for `GetMoleculeTestCounts`); FE 324 tests pass (+37 new across V1 + V1.5); `pnpm exec tsc --noEmit` clean.

**Design + plans:**
- Design: `/Users/sidx/.claude/plans/lets-look-at-our-lazy-nygaard.md` — full V0 → V1 → V2 → V3 architecture, persona-aware redesign.
- V1 plan: `docs/superpowers/plans/2026-05-17-collections-v1.md` — 10 TDD tasks shipped via subagent-driven execution + 1 smoke-fix follow-up + 4 V1.5 polish items.

**Behavior change:** `/collections/{id}` is no longer a flat name-only table. It now composes the same enriched-search engine `/search` uses (via a single `Collection` criterion — already shipped end-to-end on BE before this session at `_collection_clause:106`). The page renders a virtualized card grid by default (structure + ID + name + MW · cLogP · Ro5 chip + "Tested in N protocols" line when N > 0) or a compact table (structure thumb + ID + name + open-link). View mode persists to URL (`?view=table`) with localStorage fallback. A `CollectionHeader` strip below the page title carries badges (count · visibility · Frozen?), project chip, campaign provenance link, creator/org, and the view-mode toggle on the right; description on its own line. Selection across both views drives a Remove-from-collection action.

**Commits shipped this session** (hash + title):

| # | Hash | Title |
|---|---|---|
| 1 | `6fb8e42f` | chore(deps): add @tanstack/react-virtual for collection card grid |
| 2 | `2aff4738` | feat(collections): useViewMode hook — URL-state segmented control state |
| 3 | `f78873d4` | feat(collections): ViewModeToggle — segmented table/cards control (+ jest-dom test infra) |
| 4 | `98be940e` | feat(collections): useCollectionSearch — enriched molecule fetch via search engine |
| 5 | `f266b2f2` | feat(collections): MoleculeCard — structure + name + key props tile |
| 6 | `4dd7ecb0` | feat(collections): CardGrid — virtualized responsive grid of MoleculeCard tiles |
| 7 | `292d9165` | feat(collections): ResultsSurface — view-mode dispatcher (cards | table) |
| 8 | `e02ee4e2` | feat(collections): CollectionHeader — name + badges + provenance + owner |
| 9 | `e5d263f3` | feat(collections): refactor CollectionDetail — rich header + card/table dispatcher |
| 10 | `a3e68ab7` | fix(collections): V1 smoke — card grid ref timing + dup heading + table density |
| 11 | `d9dc2a26` | fix(collections): expose is_frozen + derived_from_campaign_id on API |
| 12 | `1e59378d` | feat(collections): compress chrome — single-row meta strip + drop back-link |
| 13 | `5287992f` | feat(collections): activity sparkline on MoleculeCard (auto-first-protocol) |
| 14 | `79116877` | revert(collections): drop V1.5 P3 sparkline — wrong design (random protocol, no caption) |
| 15 | `7837b3a4` | feat(collections): protocol test-count on MoleculeCard (project-scoped) |

**Card information density principle (locked in this session):** the V1.5 P3 sparkline (auto-first-protocol) was vetoed by the chemist because alphabetic-by-UUID protocol selection has no chemistry meaning and the unlabeled curve was uninterpretable at glance. Replaced with a higher-signal lower-clutter `Tested in N protocols` line. **General rule for card surfaces: information must EARN its space — counts beat values for at-glance scanning because they don't require interpretation.** See [[feedback_card_density]] if added.

**Surfaces touched:**
- `/collections/{id}` — primary user-visible change. Page chrome, view modes, header strip all new.
- BE: new use case `application/screening/get_molecule_test_counts.py` + new repo method `count_distinct_protocols_per_molecule` on `dose_response_curve_repository.py` + new endpoint `POST /api/v1/molecules/test-counts` (body `{molecule_ids: UUID[], project_id: UUID | None}`; response `{counts: dict[str, int]}`). `CollectionResponse` now includes `is_frozen` + `derived_from_campaign_id`.
- FE: new components/hooks under `frontend/src/features/research-organization/`:
  - `components/results/{molecule-card,card-grid,results-surface,view-mode-toggle}.tsx`
  - `components/collection/collection-header.tsx`
  - `hooks/{use-collection-search,use-protocol-test-counts}.ts`
  - `lib/use-view-mode.ts`
- FE deps: `@tanstack/react-virtual` (prod) + `@testing-library/jest-dom` (dev) + `frontend/vitest.setup.ts`.

**Smoke checklist (pending — please run before push):**

| # | Scenario | Expected |
|---|---|---|
| 1 | Open a collection with ≥3 mols on a hard-reload | `CollectionHeader` shows name in DetailShell title row + action buttons; below it a single-row strip with badges (count · visibility) · project chip · creator · view-mode toggle on the right. Description on its own line below. **NO duplicate name**. Cards default; each tile = structure + ID + name + MW · cLogP · Ro5 chip. If the mol has DR data in any protocol, a small grey `Tested in N protocols` line appears below props. |
| 2 | Click table-view icon | Switches to AG Grid with 72px rows. Structure column ~120px wide, thumbs centered + readable. ID + name + open-link columns. URL gains `?view=table`. Refresh persists. |
| 3 | Open a frozen collection (set `is_frozen=true` in DB) | Header now shows the `Frozen` chip (was previously missing — V1.5 P1 fixed this). |
| 4 | Open a campaign-derived collection (`derived_from_campaign_id` set) | Header shows `from campaign` link routing to `/campaigns/{id}` (V1.5 P1 fixed). |
| 5 | Open a collection scoped to a project | The `Tested in N protocols` line counts ONLY protocols in that project (project_id is in the protocol's project list). Sanity-check vs the DB. |
| 6 | Open a workspace-wide collection (no project_id) | Count is workspace-wide. |
| 7 | Open a brand-new untested collection | `Tested in N protocols` line is ABSENT on every card (N=0 → no line). Cards stay clean. |
| 8 | Multi-select 2 tiles → Remove → confirm | Removed; molecule count badge updates; selection clears. |
| 9 | Click a tile (not the checkbox) | Routes to `/compounds/{id}`. |
| 10 | Open an empty collection | "No molecules to display." empty state in both card and table views. |
| 11 | Click `Export SDF` on a non-empty collection | Existing SDF export runs. |
| 12 | Refresh `/collections/{id}?view=table` | Table view immediately, no flash of cards. |

**How to resume:**
1. Spin up the dev stack: `docker compose up -d && cd frontend && pnpm dev`. Verify the Temporal worker is up (`docker compose logs temporal-worker | tail`) and that the BE has reloaded the new `/api/v1/molecules/test-counts` endpoint (curl it with a known mol_id from a project to sanity-check).
2. Walk the smoke checklist above on at least one project-scoped collection AND one workspace-wide collection.
3. If anything breaks, capture the failed request payload from devtools + the row from `select id, name, project_id, is_frozen, derived_from_campaign_id from collections where id = '<id>';` for diagnostics.
4. If all smokes pass, push `prot-2` and open a PR against `main`. The prior session's commits (export pipeline + DR display honesty + multi-run aggregation) ride along — title the PR scoped to "Collections V1 redesign" and call out the prior session's commits in the body.

**Open follow-ups (post-merge):**

- **V1.5 leftovers** (small, low-risk):
  - Lift the full `/search` `ResultsGrid` into `ResultsSurface` as the table mode (today's table is a thin DataGrid without activity columns / intercept cells / aggregation toolbar).
  - Wire `<SearchQueryBuilder>` inline on `/collections/{id}` so chemists can add criteria on top of the implicit collection scope.
  - Inline-edit collection name (click-to-edit pattern; existing edit dialog stays as fallback).
  - Disable add/remove buttons when `is_frozen=true` (data is there post-P1; just needs the UX wire-up).
  - Hoist `ViewModeToggle` + view modes onto `/search` standalone.

- **V2 — scaffold tree** (the next chemist-value pop):
  - BE: `bemis_murcko_smiles` column on `Molecule` + compute at registration + backfill script.
  - BE: `POST /api/v1/scaffold-tree` using `rdScaffoldNetwork.CreateScaffoldNetwork`. Cache by mol-id-set hash.
  - FE: split-pane scaffold view (tree left, mols right). Node coloring respects page-level `AggregationControl`.

- **V3 — cluster map + heatmap:**
  - BE: UMAP-on-Morgan-FP pipeline (`umap-learn` + optional Butina) via Temporal workflow for large sets.
  - BE: `POST /api/v1/embeddings/umap` endpoint.
  - FE: `ClusterMapView` (Plotly scatter + lasso → "Save as new collection") + `HeatmapView` (AG Grid cellStyle).

**Diagnostic anchors:**
- `frontend/src/features/research-organization/components/collection-detail.tsx::CollectionDetail` — page composition: header + ResultsSurface + dialogs. Uses `useCollectionSearch` for molecules + `useProtocolTestCounts` for the count line; passes `collection.project_id` to the latter for project scoping.
- `frontend/src/features/research-organization/hooks/use-collection-search.ts::useCollectionSearch` — single source of truth for the molecule list. Posts a single `{type: "collection", collection_id}` criterion to `/api/v1/search/execute`. NO `protocol_columns` (sparkline plumbing was reverted in V1.5 P4).
- `frontend/src/features/research-organization/hooks/use-protocol-test-counts.ts::useProtocolTestCounts` — keyed by (molecule_ids sorted, project_id). Posts to the new BE endpoint; returns `{mol_id: count}`. Sort-key normalization prevents cache misses on caller-order variance.
- `frontend/src/features/research-organization/components/results/results-surface.tsx::ResultsSurface` — view-mode dispatcher. `showToolbar` prop lets the page-level chrome (CollectionDetail) own the toggle externally (collections) OR let ResultsSurface render it internally (future `/search` use).
- `frontend/src/features/research-organization/components/results/card-grid.tsx::CardGrid` — virtualized responsive grid. parentRef is on the always-mounted outer div (fixes the V1 first-load ref bug); jsdom-fallback path renders non-virtualized when `useVirtualizer` returns no items (test env only).
- `frontend/src/features/research-organization/components/results/molecule-card.tsx::MoleculeCard` — single tile. Renders `Tested in N protocols` only when `protocolCount > 0` (zero-count = no line, cards stay clean for fresh-territory compounds).
- `frontend/src/features/research-organization/components/collection/collection-header.tsx::CollectionHeader` — single-row strip with `rightSlot` for caller-provided toolbar. No H1 (DetailShell owns the page title to avoid the duplicate-heading bug fixed in V1 smoke).
- `frontend/src/features/research-organization/lib/use-view-mode.ts::useViewMode` — URL state via `?view=`. Mirrors the existing `useAggregationMode` pattern.
- `backend/src/cellar/application/screening/get_molecule_test_counts.py::GetMoleculeTestCounts` — counts distinct protocols per mol via DR-curve → run → protocol path. Many-to-many project scoping via `protocol_projects` join table.
- `backend/src/cellar/infrastructure/persistence/sqlalchemy/screening_assay/dose_response_curve_repository.py::count_distinct_protocols_per_molecule` — single SQL query. Always returns a complete dict (every requested mol_id is keyed, 0 if no curves).
- `backend/src/cellar/interface/routes/molecules.py` (or wherever the new route landed — search the codebase for `test-counts`) — `POST /api/v1/molecules/test-counts`.

**Open caveats / known limitations:**
- The card surface deliberately does NOT show any activity *value* at glance. Per the locked card-density principle ("counts beat values for scanning"), the EC50 number remains exclusive to drill-in surfaces (table view, molecule detail, /search).
- The new `/api/v1/molecules/test-counts` endpoint fires once per page open + once per filter change. No batching across collections — fine for current usage, may need debouncing if we later add inline filtering on `/collections`.
- Table-view of `/collections/{id}` is a thin DataGrid (struct + ID + name + open-link). Activity columns + intercept cells live in `/search`'s grid only. Lift task is V1.5 leftover above.
- The duplicate-heading bug fix removed the `<h1>` from `CollectionHeader`, so callers reusing `CollectionHeader` standalone (outside a DetailShell) would render no name. Currently only `CollectionDetail` uses it, and that's wrapped in DetailShell — so no callers are broken. If anyone else adopts `CollectionHeader`, they need to provide their own page title.
- `protocol_projects` is the join table that gates project scoping. If protocols ever lose their project_ids[] list (e.g. become workspace-only), the project-filter parameter silently returns 0 counts — defensive zero-init in the repo prevents undefined behavior.
- 4 BE API integration tests for `POST /api/v1/molecules/test-counts` are written but require the Docker+RDKit testcontainer to run (typical for this codebase). The 4 unit tests for `GetMoleculeTestCounts` pass without the container.

### 2026-05-16 — Unified export pipeline shipped on prot-2

**Branch:** `prot-2`. 21 implementation commits since plan commit `b20796b7` (T1–T20) + 1 test-infra fix (T21). Nothing pushed. **Browser smoke pending** (BE 2611 tests pass, FE 287 tests pass, tsc clean).

**Spec:** `docs/superpowers/specs/2026-05-16-unified-export-design.md`. **Plan:** `docs/superpowers/plans/2026-05-16-unified-export.md` (21 tasks shipped via subagent-driven execution).

**Behavior change:** Export on `/search` now runs ALWAYS-ASYNC on the backend (Temporal workflow → fsspec storage → polled by the FE → auto-download). Exports the FULL result set, not just the page loaded in the AG Grid. Four formats: CSV (machine-tabular), SDF (RDKit SDWriter + per-activity data tags), XLSX (numeric cells + embedded matplotlib sparkline PNGs up to 5K rows), PDF (WeasyPrint + Jinja landscape template, capped at 5K rows). Old `POST /api/v1/molecules/export/sdf` returns 410 with a redirect message. Old FE-only `data-grid/export-toolbar.tsx` deleted; 4 grid callers stripped of `exportFilename` / `excelEnhancer` props (export buttons gone from those grids; they'll be re-wired to the BE pipeline in follow-up PRs). T21 also added `TEMPORAL_DISABLED=1` to the API test conftest so `NullExportOrchestrator` is wired during tests (the Protocol cannot be reflection-built by Lagom).

**Commits shipped this session** (hash + title):

| # | Hash | Title |
|---|---|---|
| 1 | `445153e9` | feat(domain): ExportJob aggregate + repository protocol |
| 2 | `03fb97c5` | fix(domain): tighten ExportJob state-machine guards + Protocol typing |
| 3 | `6d085524` | feat(persistence): migration 036 — export_jobs table |
| 4 | `5408c8dd` | feat(persistence): ExportJob SQLAlchemy model + repo impl |
| 5 | `b34d3c1a` | feat(di): wire export domain repository |
| 6 | `ada19928` | feat(export): RowStream protocol + ColumnSpec + ExportRow |
| 7 | `e04def21` | feat(export): SearchResultsRowStream — cursored re-runs of ExecuteSearch |
| 8 | `4c7c7d85` | feat(export): CSV renderer + ExportRenderer protocol |
| 9 | `04a67177` | feat(export): SDF renderer (RDKit SDWriter + per-activity data tags) |
| 10 | `d5f0c48e` | feat(export): XLSX renderer — numeric cells + embedded sparklines ≤5K rows |
| 11 | `ecb595db` | feat(export): PDF renderer (WeasyPrint + Jinja template) |
| 12 | `c97a8fd0` | feat(export): RenderExport runner — streams batches, writes via fsspec, marks job ready |
| 13 | `72819490` | feat(export): start/get/cancel/list/purge use cases |
| 14 | `17dfdc62` | feat(temporal): ExportWorkflow + activity + orchestrator (Temporal + Null) |
| 15 | `b7dc1f51` | feat(di): wire export use cases + orchestrator + render runner |
| 16 | `efe06053` | feat(api): /api/v1/exports endpoints + legacy SDF 410 shim |
| 17 | `453d3bc5` | chore(api): regenerate orval client for /api/v1/exports |
| 18 | `fc4f481b` | feat(export): useExport hook + types (poll → trigger download) |
| 19 | `2f6ba60c` | feat(export): shared ExportToolbar + Sonner progress toast |
| 20 | `7228969c` | feat(search): wire new ExportToolbar — exports run server-side over full result set |
| 21 | `d12da589` | refactor(data-grid): drop FE-only export toolbar in favor of shared BE-driven one |

**T21 (this session — test-infra):**
- `tests/api/conftest.py` — added `os.environ["TEMPORAL_DISABLED"] = "1"` so the Lagom container binds `NullExportOrchestrator` during API tests instead of failing to reflect-build the `ExportOrchestrator` Protocol. This was the only failing test (`test_export.py::TestStartExport::test_returns_job_id`); all 15 API export tests now pass.

**Surfaces touched:**
- `/search` results grid — primary user-visible change: new `<ExportToolbar />` in toolbarActions; replaces old FE-only excel/csv and the 10K-cap SDF endpoint.
- 4 other grids lost their export buttons in T21 (run-dr-results, readout-data-table, activity-tab, molecule-list); will be re-wired to the BE pipeline in follow-up PRs.
- BE: new `domain/export/`, `application/export/`, `infrastructure/temporal/{workflows,activities,orchestrators}/export.py`, `infrastructure/persistence/sqlalchemy/export/`, migration 036, REST routes at `/api/v1/exports*`, legacy `/molecules/export/sdf` → 410.
- FE: new `shared/components/export/{types.ts, use-export.ts, export-toolbar.tsx, export-job-toast.tsx}`.

**Smoke checklist (pending — please run before push):**

| Scenario | Expected |
|---|---|
| Search returns 50 mols → Export → CSV | Toast spins ~1s; .csv downloads; opens cleanly; numbers are numbers; ND for inactive intercepts. |
| Same search → Export → SDF | .sdf opens in any chemistry viewer; each entry has `> <Mtb_WCA::EC50>` tags. |
| Same search → Export → Excel | .xlsx opens in Excel; numeric cells right-aligned; sparkline images appear in the Plot column (≤5K rows). |
| Same search → Export → PDF | .pdf opens; landscape; query summary + footer page numbers visible. |
| Search returns 2,500 mols → Excel | Progress toast climbs to 100%; file ~10–25 MB; opens. |
| Search returns 10,000 mols → PDF | Job marks `failed` with `"exceeds 5000 cap"` toast. |
| Click Cancel mid-export | Toast switches to "cancelled". |
| Close browser tab mid-export, re-poll later | Job still completes server-side; re-downloadable from `GET /api/v1/exports/{id}/download` (no UI tray yet — call from devtools). |
| Legacy `POST /api/v1/molecules/export/sdf` from old client | Returns 410 with JSON pointing at the new endpoint. |

**How to resume:**
1. Spin up the dev stack: `docker compose up -d && cd frontend && pnpm dev`. Verify Temporal worker is up (`docker compose logs temporal-worker | tail`).
2. Open `/search`, run any query that returns ≥3 results, click Export → CSV. Toast should show progress; file should download.
3. Walk the smoke checklist above. If anything breaks, capture the failed job's row from `select * from export_jobs order by requested_at desc limit 5;` for diagnostics.
4. If all smokes pass, push `prot-2` and open a PR against `main`.

**Open follow-ups (post-merge):**
- Port runs / batches / activity / collection grids to the new shared toolbar (each its own PR — they lost their export buttons in T21).
- Build the "Recent Exports" tray UI consuming `GET /api/v1/exports` (data is there, no UI yet).
- Schedule `PurgeExpiredExports` (the use case exists; needs a Temporal scheduled workflow or cron).
- S3 / MinIO swap of fsspec when storage volume warrants.

**Diagnostic anchors:**
- `backend/src/cellar/application/export/render_export.py::RenderExport` — single in-process runner. Both the Temporal activity and the Null-orchestrator fire-and-forget path invoke this. Streams row_stream → renderer → fsspec upload → mark_ready.
- `backend/src/cellar/application/export/row_streams/search_results.py::SearchResultsRowStream` — re-runs `ExecuteSearch` per page via cursor; builds dynamic columns from `protocol_columns` tokens (`drc:` + `rd:`); emits one `image_curve` column per DR readout.
- `backend/src/cellar/application/export/renderers/{csv,sdf,excel,pdf}_renderer.py` — one renderer per format. Each consumes the same `ColumnSpec[]` + `ExportRow` shapes; CSV/SDF skip `image_curve` columns.
- `backend/src/cellar/application/export/renderers/sparkline.py::render_sparkline_png` — single matplotlib helper shared by XLSX (PNG) and (TODO) PDF (SVG). 4PL fit gated on `curve_class != "inactive"`, matching the FE `DoseResponseFigure`.
- `backend/src/cellar/infrastructure/temporal/workflows/export.py::ExportWorkflow` — single activity, 30-min start-to-close timeout, 3 retries. No continue-as-new today (5K-row PDF cap + workflow scope keep history small; revisit if XLSX/CSV exports start pushing >50K rows).
- `backend/src/cellar/interface/routes/export.py` — POST `/api/v1/exports`, GET `/api/v1/exports/{id}`, POST `/api/v1/exports/{id}/cancel`, GET `/api/v1/exports`, GET `/api/v1/exports/{id}/download` + legacy `POST /api/v1/molecules/export/sdf` → 410.
- `frontend/src/shared/components/export/use-export.ts::useExport` — single hook every export caller uses. Polls 500ms then 2s backoff; triggers `<a download>` on ready; reset clears state.
- `frontend/src/shared/components/export/export-toolbar.tsx::ExportToolbar` — single dropdown. Consumers hand it a `buildRequest(format) => ExportRequest | null`.

**Open caveats:**
- No "Recent Exports" tray UI; chemists who close their browser mid-export can re-download by hitting `GET /api/v1/exports/{id}/download` directly (or polling `GET /api/v1/exports` from devtools).
- Continue-as-new isn't wired on `ExportWorkflow` — the 30-min activity timeout caps how big a single export can get. For real `>100K`-row exports we'd batch the activity.
- PDF renderer materializes all rows into memory before WeasyPrint (forced by WeasyPrint's API). CSV/SDF/XLSX stream batch-by-batch.
- The `application/orchestration` package has a pre-existing typo (`WorkflowOrchestratorUnavailable` imports it via re-export). Untouched.
- Sparklines in XLSX/PDF read `row.raw["activity"]["curve_snapshot"]`, but `SearchResultsRowStream._row_for` builds `raw["activity"]` from the activity_data dict that `ExecuteSearch` returns — that dict already carries `curve_snapshot` from the existing `_build_curve_snapshot` shared module. **Validate during smoke that sparkline PNGs actually render in the XLSX** — if cells are blank, the activity dict shape doesn't carry `curve_snapshot` at the right depth and the renderer needs a one-line fix.

### 2026-05-15 — Multi-run aggregation in search & Activity surfaces on `prot-2`

**Branch:** `prot-2`. 15 commits ahead of the 2026-05-14 handoff HEAD (`465f3daa`); `git rev-list --count 465f3daa..HEAD` = 15. Nothing pushed. **Browser smoke pending** (test grid + tests passed: BE 2539, FE 214, tsc clean).

**Spec:** `docs/superpowers/specs/2026-05-15-multi-run-aggregation-plan.md` (15 tasks shipped via subagent-driven execution, two-stage review per task).

**Behavior change:** the search results grid + molecule/protocol Activity tabs no longer silently pick the best-R² curve when a compound has multiple runs in a protocol. Default is now LATEST_APPROVED_RUN (matches campaign default + chemist mental model). Toolbar lets chemists switch to Geometric mean / Mean / Best R².

**Commits shipped this session** (hash + title; full details via `git log`):

| # | Hash | Title |
|---|---|---|
| 1 | `1bf5c9ed` | refactor(domain): lift selection-rule types to shared; add AggregateStats |
| 2 | `a5465647` | docs(domain): clarify enums.py re-export points to shared, not screening_assay |
| 3 | `60e744e9` | feat(screening): shared run-aggregation module — selection rules + chemistry-honest stats |
| 4 | `474a8b33` | refactor(screening): run_aggregation polish from code review |
| 5 | `3b843276` | refactor(campaign): channel_resolver delegates to shared run_aggregation |
| 6 | `428b00b6` | refactor(screening): Task 3 code-review polish |
| 7 | `ba8bda68` | feat(domain): ActivityValue carries multi-run aggregation context |
| 8 | `f7a85584` | feat(screening): RunScope VO + find_all_curves_for_molecules repo method |
| 9 | `39473a2c` | feat(search): enrich_molecules aggregates over all in-scope runs |
| 10 | `6d40aa29` | feat(search): API exposes aggregation rule + per-criterion run_scope |
| 11 | `0cb34230` | feat(search): AggregationMode type + URL state hook |
| 12 | `7d21be55` | feat(search): toolbar AggregationControl picks selection rule |
| 13 | `029e0a74` | feat(screening): formatInterceptDisplay carries multi-run decoration |
| 14 | `b030ada9` | feat(search): InterceptCell with Popover drill-in for multi-run cells |
| 15 | `7c8cccab` | feat(search): saved searches persist aggregation rule via query payload |

**Surfaces touched:**
- Search results grid (research_organization) — primary user-visible change
- Molecule detail Activity tab + Protocol hub Activity tab — share the same `enrich_molecules` so they pick up the new behavior automatically
- Saved searches — round-trip the new `aggregation` field embedded in `query` JSONB
- Campaign behavior unchanged — channel resolver shares the same aggregator but its own selection rule, qualifier handling, and snapshot machinery

**Per-cell wire shape additions on `ActivityValue`:**
- `run_count: int` (default 1)
- `selection_rule: str | None`
- `runs: list[RunSummary] | None` — capped at 10 most recent for tooltip drill-in
- `intercept_aggregates: list[InterceptAggregate]` — per-intercept selected_value/qualifier/stats/disagreement
- `disagreement_flag: bool` — ⚠ trigger from log-range >1 OR mixed Inactive

**Cell visual contract:**
- `value · unit` — baseline
- `value · unit · ₙ` — multi-run (subscript = run count)
- `value · unit · ₙ · ×N` — gmean/mean mode (chip = fold-range)
- `value · unit · ₙ · ⚠` — disagreement (log-range >1 OR mixed Inactive)
- `ND · ₙ` — all-Inactive
- Click on a multi-run cell opens a Popover with per-run table (date · value · R² · class) + stats footer (geometric mean · fold-range · log10-value mean ± sample SD)

**Smoke checklist (pending — please run before push):**

| Scenario | Expected |
|---|---|
| Open search with default mode | Toolbar shows "Show: Latest run". URL has no `?agg=` param. |
| Compound with 1 run | Cell shows just `value · unit`. No subscript, no warning, no Popover trigger. |
| Compound with 3 runs (all active, tight) | Cell: `value · unit · ₃`. Click opens Popover with 3 dated rows + stats footer. |
| Compound with 4 runs, 1 Inactive | Cell: `value · unit · ₄ · ⚠`. Popover shows the Inactive run as ND. |
| Compound with 3 runs spanning >1 log unit | Cell: `value · unit · ₃ · ⚠`. Stats footer shows fold-range > 10. |
| Compound with all runs Inactive | Cell: `ND · ₅`. |
| Switch toolbar to Geometric mean | Cells refetch. Multi-run cells show `gmean · unit · ×N · ₃`. URL: `?agg=gmean`. |
| Switch back to Latest | URL strips `?agg=`. Cells return to latest values. |
| Set per-criterion run_scope to "Last 3 runs" | Cell run-count caps at 3 across compounds. |
| Save the search with non-default aggregation | Reload the saved search → toolbar shows the same mode. |
| Open the same compound's molecule-detail Activity tab | Cells use the same display + tooltip behavior (default Latest). |
| Open a campaign that channels from this protocol | Campaign cells are unchanged (still the campaign's own selection_rule). |

**Diagnostic anchors:**
- `application/screening/run_aggregation.py` — single source of truth for selection rules + chemistry-honest variance stats. Both campaign resolver and search aggregator consume it. `_pick_one_resolvable` (renamed from `_pick_one_eq`) admits EQ + GT-from-at_bound; aggregating rules use `intercept_scalar` (EQ-only). Sample SD via Bessel's correction (n-1 divisor).
- `domain/shared/aggregation_types.py` — real home of `SelectionRule` (now includes `BEST_R_SQUARED`), `QualifierHandling` (kept `TREAT_AS_LIMIT`), `ValueQualifier` (kept `EXCLUDED`; chemistry-symbol values `=`/`</`/`>` preserved), `AggregateStats`. Lifted to `shared/` because the import-linter Bounded Context Independence contract forbids `research_organization → screening_assay` imports. Re-exports at `domain.research_organization.enums` and `domain.screening_assay.aggregation_types` so existing imports keep working.
- `application/screening/molecule_activity_service.py` — `enrich_molecules` accepts `selection_rule`, `qualifier_handling`, `run_scopes` keyword args. Default = `LATEST_APPROVED_RUN` + `EXCLUDE_QUALIFIED`. `_build_resolved_runs` adapts `DoseResponseCurve + Run` to `ResolvedRun`. `runs[]` capped at 10 most recent for the tooltip; aggregate stats computed over ALL in-scope runs.
- `domain/screening_assay/run_scope.py` — tagged-union VO covering all/last_n/since/between/run_ids. `last_n` applied per-(mol, rd) after grouping (not as a global SQL LIMIT).
- `infrastructure/persistence/sqlalchemy/screening_assay/dose_response_curve_repository.py::find_all_curves_for_molecules` — joins to `RunModel` for run_date filtering; returns `{mol: {rd: [curves desc]}}`.
- `application/research_organization/execute_search.py::_collect_run_scopes` — walks the criteria tree to find per-protocol-criterion run_scopes; applies them uniformly to all DR columns (single-criterion case) or last-wins (multi-criterion). `_parse_run_scope` matches the FE's `{mode: ...}` wire shape (latest / past_n_days / specific / date_range / any / all).
- `interface/routes/search.py::ExecuteSearchBody.aggregation` — typed as `SelectionRule`, defaults to `LATEST_APPROVED_RUN`. Passes through `ExecuteSearchQuery.aggregation`.
- `frontend/src/features/research-organization/lib/use-aggregation-mode.ts` — URL state hook + wire mappers. Short form (`latest`/`gmean`/`mean`/`best_r2`) omitted from URL at default. Includes pub/sub for cross-subscriber sync (added during Task 9 because `window.history.replaceState` doesn't notify `useSearchParams` consumers).
- `frontend/src/features/research-organization/components/search/intercept-cell.tsx` — `<InterceptCell />` wraps the existing display logic + adds subscript / fold-range chip / `<AlertTriangle>` disagreement glyph / Popover drill-in. Single-run cells skip the Popover.
- `frontend/src/features/research-organization/components/search/run-history-tooltip.tsx` — per-run table + stats footer rendered inside the Popover.
- `frontend/src/features/screening-assay/lib/intercept-label.ts::formatInterceptDisplay` — extended additively with optional `runCount`/`mode`/`foldRange`/`disagreement` inputs + new `primary`/`decoration` outputs. The 3 production callers (`run-dr-results-columns`, `readout-data-table`, `activity-tab-columns`) read `.text`/`.kind`/`.warning` unchanged.
- `domain/screening_assay/activity_types.py` — `ActivityValue` extended with multi-run fields; new `RunSummary`, `InterceptAggregate` dataclasses. `AggregateStats` imported from `aggregation_types` (no duplication).

**Open caveats / known limitations:**
- `_filter_by_qualifier_handling` raises `NotImplementedError` on `TREAT_AS_LIMIT` (no defined semantics in shared aggregator). Use `EXCLUDE_QUALIFIED` or `INCLUDE_QUALIFIED` until search/campaign agree on a unified rule.
- Intercept-spec discovery uses the union of `(kind, level)` from candidate curves' `intercept_values` (pragmatic — avoids a separate protocol-side fetch). Edge case: intercepts at levels exactly 0 or 100 are silently dropped by `InterceptKey.__post_init__` validation. Doesn't affect real protocols.
- `_pick_one_resolvable` admits EQ + GT-from-at_bound for LATEST_APPROVED_RUN / BEST_R_SQUARED, so an at_bound LATEST run surfaces as `>max_dose` (not ND). Aggregating rules still drop non-EQ. This was a code-review fix to preserve campaign behavior.
- Popover drill-in is click-trigger (not hover) — HoverCard isn't in this codebase; Popover was the simplest replacement. Click-trigger is also keyboard-accessible. If chemists want hover, a follow-up can wrap the trigger.
- Dead code: `renderInterceptCell` at `results-grid.tsx:188` is now unreferenced. Left in place for one cleanup commit.
- Subtle: aggregate-mode `representative_run` now picks from EQ contributors only (was: latest of any post-QC candidate). New behavior is more defensible (snapshot reflects what actually contributed). Surfaces only on aggregate channels with mixed EQ/Inactive runs — flagged in commit `474a8b33`.

**How to resume:**
1. Run the smoke checklist above on the dev stack (`docker compose up -d && cd frontend && pnpm dev`). Recommended fixture: a protocol where at least one compound has 3+ runs (e.g. `Mtb_WCA_mc2-7000_Resazurin` if available).
2. Push `prot-2` and open a PR against `main`.
3. Optional cleanup commit: remove dead `renderInterceptCell` from `results-grid.tsx` once the smoke confirms `<InterceptCell />` handles all cases.

**Follow-up shipped (commits 17–18):** chemist surfaced a gap on the campaign grid — switching a channel to MEAN updated the EC50 value but the chart still drew the latest run's curve with its (now-mismatched) per-curve intercept line. Fixed end-to-end:

- `5e182dbc feat(campaign): aggregate-mode curve_snapshot carries all contributing curves + marker` — extends the JSONB snapshot in aggregate modes with `additional_curves[]` (each non-rep contributor with run_id + run_date) and `aggregate: {marker_x, marker_label, unit}`. Touches `_build_aggregate_curve_snapshot` (new helper in `channel_resolution.py`) + both resolver paths (`channel_resolution.ChannelResolver.resolve` and `preview_run_import._apply_selection_rule`). LATEST and BEST_R_SQUARED cells unchanged on the wire. Tests: +9 in `test_channel_resolver.py`, +5 in `test_preview_run_import.py`; 232 research_org tests pass.
- `e16285a1 feat(campaign): aggregate-mode chart overlays contributing curves + marker` — extends `CurveSnapshot` FE type, adds `AdditionalCurve` + `AggregateMarker`. `DoseResponseFigure.buildPlotInputs` draws each non-inactive additional curve as a muted dashed sigmoid (~0.35 opacity), and in aggregate mode replaces the per-curve dashed intercept line with a single solid amber line at `aggregate.marker_x`. Inactive overlays skipped; marker still draws. `DoseResponseSparkline` and the campaign grid call site pass the new fields. Tests: +5 in `dose-response-figure.test.tsx`; 223 FE tests pass.

**Scope of the follow-up:** thumbnail only. The campaign expand-dialog uses `DoseResponseChart` + `snapshotToDoseResponseCurve` adapter (a different path) and still renders the rep curve only on click-expand. Defer unless chemists ask — the inline thumbnail is what was visible in the bug report.

**Browser smoke for the follow-up:** open a closed campaign with a MEAN or GMEAN channel that has 2+ contributing runs. Thumbnail should show: primary fit (solid, full opacity) + N muted dashed sibling fits + a single solid amber vertical line at the cell's aggregate value (NOT at the rep's fitted_value). LATEST-mode and single-run cells unchanged.

### Open follow-ups (handoff to fresh session)

The overlay/marker treatment from commits 17–18 lives only in the campaign Curve column's thumbnail. Two surfaces still show the misleading rep-only curve when an aggregate is displayed. Both fixes are pure additive work on top of the now-shipped BE shape (`curve_snapshot.additional_curves[]` + `aggregate.{marker_x, marker_label, unit}`).

**Follow-up A: Campaign expand-dialog (FE-only)**

When chemist clicks the Curve thumbnail on an aggregate-mode cell, the modal that opens still renders the rep curve only — no overlay, no aggregate marker.

- Surface: `frontend/src/features/screen-campaign/components/grid/curve-expand-dialog.tsx`
- Path: `<CurveExpandDialog>` → `snapshotToDoseResponseCurve(snap, ctx)` → `<DoseResponseChart>`
- Files to touch:
  - `frontend/src/features/screen-campaign/lib/snapshot-adapter.ts` — `snapshotToDoseResponseCurve` currently drops `snap.additional_curves` + `snap.aggregate`. Extend the returned `DoseResponseCurve` (or wrap with overlay info) so the chart receives them.
  - `frontend/src/features/screening-assay/types/index.ts` — extend `DoseResponseCurve` with optional `additional_curves?: AdditionalCurve[]` + `aggregate?: AggregateMarker` mirroring what `CurveSnapshot` already has.
  - `frontend/src/features/screening-assay/components/dose-response-chart.tsx` (1063 LOC) — has its own Plotly rendering separate from `DoseResponseFigure`. Apply the same logic Task 18 added to `buildPlotInputs`: muted dashed sigmoid per non-inactive `additional_curve`, single solid line at `aggregate.marker_x` in aggregate mode (suppress the per-curve intercept dashes). The SummaryCard headline label could also surface "mean" / "gmean" + N when `aggregate` is present.
- Reference implementation: see `dose-response-figure.tsx::buildPlotInputs` post-commit `e16285a1` for the exact overlay + shape construction pattern.
- Out of scope: BE shape (already shipped).

**Follow-up B: Search results grid (BE + FE)**

When chemist switches the search toolbar's aggregation to "Geometric mean" or "Arithmetic mean" with multi-run compounds, the per-cell Plot thumbnail still shows the rep curve only. The cell-value summary (gmean ± SD, pIC50, etc.) IS correct — only the chart is stale.

- Surface: `frontend/src/features/research-organization/components/search/results-grid.tsx` — the DR column's cellRenderer renders a chart via `<DoseResponseSparkline>` / `<DoseResponseFigure>` (shared with campaigns, so once BE writes the fields the FE renders them automatically — see Task 18).
- **Key BE gap:** `MoleculeActivityService.enrich_molecules` builds `ActivityValue.raw_data` + `ActivityValue.curve_params` from the representative `ResolvedRun` only. It does NOT populate `additional_curves` or `aggregate` on the wire when `selection_rule` is MEAN/GMEAN.
- Files to touch:
  - `backend/src/cellar/application/research_organization/channel_resolution.py` — **lift `_build_aggregate_curve_snapshot` to a shared module** so both campaigns and search can use it. Suggested home: `backend/src/cellar/application/screening/curve_snapshot.py` (new). Keep a back-compat re-export in `channel_resolution.py`.
  - `backend/src/cellar/application/screening/molecule_activity_service.py` — when `selection_rule in {MEAN_ACROSS_RUNS, GEOMETRIC_MEAN}`, call the lifted `build_aggregate_curve_snapshot(candidates, aggregate_value=..., aggregate_label=...)` and add the result to the wire payload. Likely needs a new field on `ActivityValue` (`curve_overlay?: {additional_curves, aggregate}`) — or extend `curve_params` + `raw_data` shape.
  - `backend/src/cellar/domain/screening_assay/activity_types.py` — add the new field to `ActivityValue` dataclass.
  - `frontend/src/features/research-organization/types/index.ts` — mirror the new wire field on the FE `ActivityValue` interface.
  - `frontend/src/features/research-organization/components/search/results-grid.tsx` — pass the new field into the chart sparkline.
- Tests: extend `tests/unit/application/screening/test_molecule_activity_service.py` to cover MEAN/GMEAN modes writing the overlay; FE tests for the new wire field passthrough.

**Bonus low-cost fix:** the lift to a shared `curve_snapshot.py` cleans up the cross-context dependency that `preview_run_import.py` already has on `channel_resolution.py`. Worth doing for code hygiene even before Follow-up B.

### 2026-05-14 — DR curve identity refactor + dynamic intercept columns on `prot-2`

**Branch:** `prot-2`, `git rev-list --count e807dd03..HEAD` commits ahead of the merged `fe2` HEAD. Nothing pushed yet. Dev DB at head migration `035_cc_intercept_key`. Live snapshot rebuild has been run (`rebuild_campaign_curve_snapshots.py --include-closed`) so existing closed campaigns now carry the full chart shape.

**Spec:** `docs/superpowers/specs/2026-05-13-dynamic-intercept-columns-design.md` (8 surfaces shipped, all acknowledged as done modulo browser smoke).

**Commits shipped this session** (full detail in `git log`; this list is hash + one-line "what" + key tests/migrations only):

| # | Hash | Title | Notes |
|---|---|---|---|
| 1 | `32da062c` | refactor(screening): identify DR curves by readout-def, not curve_type | Migrations 033 + 034. Truncates `dose_response_curves`; resolver + 3 reader queries flip to `readout_definition_id`. |
| 2 | `19ed9253` | chore(screening): refit-all script | Ran live, restored 40 curves across 5 runs / 3 protocols. |
| 3 | `0d8aae80` | fix(screening): IC90/EC90 marker Y position needs level/100 | Single-line fix; was producing y≈9746 on the chart. |
| 4 | `a31bf7cc` | feat(screening): run DR table per-intercept columns (Surface #1) | New `intercept-label.ts` + 9 unit tests. |
| 5 | `5fe1e245` | feat(screening): activity tabs per-intercept columns (Surfaces #2–#3) | Both protocol-hub + molecule-activity payloads. |
| 6 | `e67b7641` | feat(search): results grid per-intercept columns (Surface #4) | `resolveColumns` over the new `drc:<rd_id>` colId shape; +7 grid tests. |
| 7 | `971c03de` | refactor(screening): chart labels via interceptLabel (Surface #5) | Single source of truth across surfaces. |
| 8 | `c92f3d11` | feat(screening): readout-data table per-intercept columns (Surface #6) | FE-only denorm. |
| 9 | `622490f8` | fix(search): detail drawer "Selected Protocols" missing on DR rows | Lifted resolver into shared `protocol-column-id.ts` (+5 tests). |
| 10 | `c561f557` | feat(screening): promote Intercepts to first-class in protocol design | Editor moves out of collapsed `<details>`; create-dialog now emits `intercepts`. |
| 11 | `db04e938` | feat(screening): hit-criteria builder targets specific intercepts (Surface #7) | New `InterceptKey` VO + `hit-criteria-options.ts`. |
| 12 | `dbc42464` | feat(search): unified Export menu (Surface #8 — scope-reduced) | CI sub-columns vetoed at smoke (see [[feedback-no-ci-subcolumns]]). |
| 13 | `73bb6f07` | feat(campaign): channel hit threshold honors intercept_key end-to-end | FE picker, defaults, display chip; +9 FE tests. |
| 14 | `0003597e` | feat(campaign): add-from-runs splits multi-intercept DR readouts per intercept | `channelConfigKey` helper; +5 FE tests. |
| 15 | `e364c07b` | fix(campaign): multi-intercept channels — proper cells, hits, labels | 3 coordinated bugs (channel-key collision + primary aggregate + label collision); +1 BE test. |
| 16 | `1c19f594` | feat(campaign): channel intercept_key as top-level field (Option A) | **Migration 035** (additive JSONB on `campaign_channel`). Decouples identity from `hit_threshold`; `_intercept_scalar` becomes the single SoT. +1 BE preview test, 4 resolver tests updated. |
| 17 | `00cf02bd` | feat(campaign): mirror protocol — bulk-create channels for every readout | New use case + `POST /channels/mirror-protocol` + `MirrorProtocolPopover`. Idempotent on `(protocol, rd, norm, ik)`. +6 BE tests. |
| 18 | `570f67b6` | feat(campaign): expand-dialog renders via shared DoseResponseChart | `_build_curve_snapshot` writes `curve_type` + `intercept_values` + CI + warnings; new `snapshotToDoseResponseCurve` adapter; dialog rewritten ~100→~50 LOC. **Backfill script** (`rebuild_campaign_curve_snapshots.py`, `--include-closed` ran). +1 BE + 4 FE tests. |
| 19 | `ec0eeb15` | fix(campaign): closed view defaults filter to Selected only | New `closedCampaignFilters()`; chemist's frame is "what made the cut". |
| 20 | `4fd9a94c` | feat(screening): formatInterceptDisplay — single rule for ND / >max / scalar | New helper in `intercept-label.ts` (SoT); +10 unit tests. Industry-anchored (CDD / ChEMBL / Genedata / Prism). R² intentionally not a separate rule — folded into `curve_class`. |
| 21 | `0e5ec227` | feat(screening): run DR grid renders ND / >max instead of fake scalars | Adopts helper. Fixes the screenshot case (CV-00982 EC50=0.01310 / EC90=0.002380 / R²=0 / Inactive). |
| 22 | `f84da6f8` | feat(screening): activity tabs render ND / >max for inactive + at-bound | Both protocol-hub + molecule-detail Activity grids. Source paths: `rv.curve_class` + `rv.data_points` at the top level of `ReadoutValue`. |
| 23 | `8b71f811` | feat(search): results grid honors the same ND / >max display rule | `renderInterceptCell` + the no-intercept fallback in `buildDrcColumns`. Wire qualifier (`av.qualifier > / <`) is suppressed in non-scalar cells. |
| 24 | `94044efa` | feat(screening): readout-data table honors the ND / >max display rule | Last of the four DR intercept cell surfaces. |
| 25 | `624c2b19` | feat(screening): DR thumbnail draws points only for Inactive curves | `DoseResponseFigure` gates the fit-trace + vertical-dash on `curve_class !== "inactive"`. +3 component tests (mocks Plot + chart-colors). Inherits everywhere via `DoseResponseSparkline` and the campaign expand-dialog. |
| 26 | `f71686f2` | fix(screening): ND / >max cells sort to where a chemist expects them | `formatInterceptDisplay` now returns `sortValue` (scalar / +Infinity / null). All 4 FE DR-grid valueGetters delegate, so AG Grid sorts scalar < qualifier < ND/missing. Tooltips spell out "ND = Not Determined". +1 ordering test. |
| 27 | `02eeb94f` | feat(research_org): resolver emits ND for inactive curves, >max for at_bound | Backend `_resolve_intercept(c, ik) -> (value, qualifier)` helper. Inactive → (None, ND); at_bound + max_dose → (max_dose, GT); healthy → (value, EQ). `_intercept_scalar` becomes a thin wrapper that drops non-EQ rows, so MEAN/GEOMETRIC aggregates stay honest. Same pattern in `preview_run_import._apply_selection_rule`. +15 unit tests; no wire-shape changes; no migration. |
| 28 | `2e14607f` | fix(campaign): grid value cell renders ND uppercase, tooltip + sort honest | Cosmetic alignment to match every other DR surface; the BE refactor in #27 also makes the campaign grid sort honest (Inactive rows now arrive as `value=null, qualifier=nd` and AG Grid sinks them in asc). |

**Verification at HEAD:**
- Backend `screening_assay` + `research_organization` subset = **729 passed** (was 712 pre-DR-honesty pass; +15 new resolver tests + 2 misc differential).
- Frontend = **170 passed** (+14 new total this thread), `pnpm exec tsc --noEmit` clean.
- Browser smoke for Surfaces #1–#7 passed on 2026-05-14. Commits #12, #14, #15, #16, #17, #18, #19, **#20–#28** still need fresh browser smokes. The campaign-grid smoke is most important now — a closed campaign with at least one Inactive measurement should now read "ND" in the value column (font-mono uppercase, hover tooltip "ND = Not Determined") instead of lowercase italic "nd" or a fake scalar.

**How to resume:**
1. **Live smoke #16** on `Mtb_WCA_mc2-7000_Resazurin` against a fresh campaign — add-from-runs with `EC50 use_for_filter:ON, <50 µM` + `EC90 use_for_filter:OFF, no threshold`. Expect `22 mols · 2 hits` (CV-00967, CV-00983), distinct EC50 vs EC90 cell numbers, HIT badges only on the EC50 column. DB check: 2 rows on `campaign_channel` for Resazurin — EC50 row `intercept_key=NULL`, EC90 row `intercept_key={"kind":"ec","level":90.0}`. Then edit the EC90 channel to add `<100` threshold and re-render → EC90 cells gain HIT badges where appropriate.
2. **Live smoke #17** on the same protocol against a *fresh* campaign with NO channels — click `[Copy] Mirror protocol`, pick the protocol, click **Mirror**. Expect `Created N channels` toast. Re-mirror → `No new channels — N already mirrored`. DB check: rows match expected shape (multi-intercept DR → 2 rows, non-DR → 1 row each with `normalization_applied` set).
3. **Live smoke #18** on the existing closed `Mtb_WCA_mc2-7000_Resazurin` campaign — click a curve thumbnail. Expand dialog should render via `<DoseResponseChart>` with intercept chip strip (EC50 + EC90), CI strip, warning badges — bit-identical to the same compound in the search compound-detail sheet. Backfill already ran so closed-campaign snapshots carry the full shape.
4. **Live smoke #19** — open the closed `Mtb_WCA_mc2-7000_Resazurin` campaign and confirm the filter bar opens with `Selected` chip pre-active and only the 2 selected molecules visible (rejected/deferred chips one click away).
5. **Smoke #12 + #14 + #15** if not already done.
6. **Live smoke #20–#25 (DR display honesty)** on `/assays/runs/0f1b3be3-bc65-44bf-882c-d08e7d4ff216#dose-response` (the screenshot URL) — CV-00982, CV-00971, CV-00968, CV-00966, CV-00973, CV-00976 all classified Inactive: their EC50/EC90 columns must read **ND** (font-mono, muted) with a tooltip "Inactive — no determination", and the Curve column thumbnails show **only data-point markers** (no fit line, no vertical dashed line). The single healthy curve in the run (whichever is non-Inactive) must be unchanged — scalar values + fit line + dash. Then visit the same compounds on the protocol-hub Activity tab, molecule-detail Activity tab, search results grid, and the Readout Data tab of the run — all four surfaces should match. Open the closed `Mtb_WCA_mc2-7000_Resazurin` campaign's expand-dialog on an Inactive row — same points-only treatment via `DoseResponseChart` (inherits from the shared figure).
7. **Push** — `prot-2` is local-only. After smokes pass: push and open a PR against `main`.

**Diagnostic anchors:**
- `frontend/src/features/screening-assay/lib/intercept-label.ts` — only place chemist-facing intercept labels are produced, cell lookups happen, **or the ND / >max / scalar display rule is decided** (`formatInterceptDisplay` + `maxDoseFromRawData`). `narrowInterceptKey` is the wire→domain narrower for orval-generated `{kind: string, ...}` → hand-typed `InterceptKey`. `InterceptDisplay.sortValue` is the SoT for AG Grid sort across every DR grid surface.
- `frontend/src/features/screening-assay/components/dose-response-figure.tsx` — `showFit = curve.curve_class !== "inactive"` gates both the 4PL fit trace and the vertical-dash shape; Inactive curves render points-only across every surface that uses this component (sparkline, run page, expand dialog, search detail).
- `application/research_organization/channel_resolution.py::_resolve_intercept` — backend twin of `formatInterceptDisplay`: emits (None, ND) for Inactive curves and (max_dose, GT) for at_bound. Single SoT feeding both the resolver (LATEST_APPROVED_RUN) and `_intercept_scalar` (aggregation), so the campaign grid stays consistent with the FE display rule without the FE needing to know about source curves on aggregate channels.
- `frontend/src/features/screening-assay/lib/hit-criteria-options.ts` — only place the hit-criteria dialog's option list is built or a rule is mapped back to an option id.
- `frontend/src/features/research-organization/lib/protocol-column-id.ts` — only place `drc:<rd_id>` / `rd:<proto>:<rd>` colIds get joined back to their owning protocol.
- `application/screening/molecule_activity_service.py::_serialize_intercept_values` — single helper feeds both the molecule-activity payload and the search-grid `ActivityValue.intercept_values`.
- `application/research_organization/channel_resolution.py::_intercept_scalar` — single helper produces the channel's per-candidate scalar from `channel.intercept_key`. `_build_curve_snapshot` in the same file is the only place a `CampaignMeasurement.curve_snapshot` JSONB is shaped.
- `application/research_organization/preview_run_import.py` + `add_results_from_runs.py` — channel-reuse key tuple's fourth element is `cfg.intercept_key` (top-level), not `cfg.hit_threshold.intercept_key`. Display-only multi-intercept channels keep identity even with `hit_threshold=None`.
- `application/research_organization/mirror_protocol_channels.py` — only place that bulk-creates channels from a protocol; same idempotency key as preview_run_import.
- `frontend/src/features/screen-campaign/lib/snapshot-adapter.ts::snapshotToDoseResponseCurve` — only place the campaign's `CurveSnapshot` is widened to the chart's `DoseResponseCurve` shape.

**Open caveat:** Multi-DR protocols (2+ DOSE_RESPONSE readout-defs with their own intercept lists) still use the *first* DR readout's intercepts on every grid. Per-readout column groups deferred until a real protocol surfaces it.

Long-lived state lives in `~/.claude` memory — see `MEMORY.md`, especially `feedback_drc_identity.md` (the "curves keyed by readout_definition_id" principle that motivated the whole refactor).
