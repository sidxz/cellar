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

### 2026-05-14 — DR curve identity refactor + dynamic intercept columns on `prot-2`

**Branch:** `prot-2`, 12 commits ahead of `e807dd03` (the merged `fe2` HEAD). Nothing pushed. Dev DB migrated to head (`034_drc_config_snapshot`).

**Spec:** `docs/superpowers/specs/2026-05-13-dynamic-intercept-columns-design.md`

**Shipped this session (in commit order):**

1. **`32da062c` — `refactor(screening): identify DR curves by readout-def, not curve_type`** (41 files, +925/−373)
   - Migration 033: `dose_response_curves.readout_definition_id` NOT NULL FK + `ix_drc_resolver` index + `uq_drc_run_well_readout` unique constraint. Truncates the table and nulls `campaign_measurement.{source_curve_id, curve_snapshot}` (no safe synthetic backfill for multi-DR protocols sharing curve_type).
   - Migration 034: `dose_response_curves.dose_response_config_snapshot` JSONB (additive, freezes the post-override config that drove each fit).
   - Domain entity, SQLA model, repo, fitter, refit, create use-case + route DTOs all carry `readout_definition_id` end-to-end. `find_best_curves_for_molecules` now keys by readout-def.
   - Channel resolver filters by `readout_definition_id` (multi-DR regression test in `tests/integration/research_organization/test_channel_resolution_query.py`).
   - Three reader queries flipped from `curve_type` filtering to `readout_definition_id`: `molecule_reader._apply_drc_sort` (`drc:{readout_definition_id}` token), `_batch_query._selectivity_clause`, `_activity_query` (criterion shape uses explicit `source: "dr_curve" | "readout_data"` + `readout_definition_id`).
   - `protocol_activity_reader` (DRAggRow / BestParamsRow) groups by readout-def, not curve_type.
   - FE: search query builder, selectivity criterion, activity criterion shapes flipped. Orval regenerated. `tsc --noEmit` clean.

2. **`19ed9253` — `chore(screening): script to refit all DR curves after migration 033`**
   - `backend/scripts/refit_all_dose_response.py` — idempotent, resumable, supports `--workspace-id` / `--protocol-id` / `--dry-run`.
   - Ran live on dev DB: 40 curves restored across 5 runs / 3 protocols. All rows carry `readout_definition_id` + `dose_response_config_snapshot`.

3. **`0d8aae80` — `fix(screening): IC90/EC90 marker Y position needs level/100`**
   - `dose-response-chart.tsx` was computing `bottom + level * (top - bottom)` for secondary intercept markers — `level` is a percentage (90 for EC90), not a fraction. EC90 marker landed at y≈9746, Plotly autoscaled to 10k%, curve looked flat. Fixed with `(level / 100)`.

4. **`a31bf7cc` — `feat(screening): run DR table renders one column per protocol intercept`** (spec Surface #1)
   - New helper `frontend/src/features/screening-assay/lib/intercept-label.ts`: `interceptLabel(spec)` + `findInterceptValue(values, spec)` + 9 unit tests.
   - `run-dr-results-columns.tsx` is now data-driven: one column per protocol intercept; primary reads `row.fitted_value` (back-compat with legacy fits); secondaries read via `findInterceptValue`; missing match shows "—" with Recompute hint; `at_bound = true` renders amber chip.
   - "Type" column dropped (column header *is* the intercept name now).

5. **`5fe1e245` — `feat(screening): activity tabs render one column per protocol intercept`** (spec Surfaces #2 + #3)
   - Backend: `BestParamsRow.intercept_values` carried up from SQL; `CurveParams.intercept_values` + `ReadoutDefInfo.intercepts` on the protocol-activity payload (`protocol_hub` route); `ProtocolActivitySummary.intercepts` + per-curve `intercept_values` on the molecule-activity payload (`molecules.py` `/activity` route).
   - FE Surface #2: `screening-assay/components/detail-tabs/activity-tab-columns.tsx` `buildColumnDefs` branches DR vs numeric. DR readouts emit N intercept columns from `rd.intercepts`, each reading from the row's `curve_params.intercept_values`.
   - FE Surface #3: `chemical-registration/components/detail-tabs/activity-tab.tsx` extracts a `CurveTable` that consumes the protocol's `intercepts`. One column per spec; cells matched on (kind, level) so protocol relabels survive.

6. **`e67b7641` — `feat(search): results grid renders one column per protocol intercept`** (spec Surface #4)
   - Backend wire-shape: `ActivityValue.intercept_values: list[dict] | None` (mirrors `CurveDetail.intercept_values`). `MoleculeActivityService._enrich_molecules` populates it via the same `_serialize_intercept_values` helper that already feeds the molecule-activity payload (extracted to keep both serializers from drifting). `asdict(v)` in `execute_search.py` carries the new field to the `/search/execute` response with no route-side change.
   - FE: `results-grid.tsx` `buildProtocolColumnGroups` rewritten around a `resolveColumns` pass that joins each `drc:<rd_id>` (2-segment, post-033) or `rd:<proto>:<rd>[:<norm>]` colId back to its owning protocol via a reverse readout-def index over `protocols[]`. Replaces the earlier `parts[1]`-based grouping that silently broke after the `drc:` colId stopped carrying a `protoId` segment.
   - Per `drc:` colId emits N intercept sub-columns from `dose_response_config.intercepts` + a single Plot column. Headers via `interceptLabel(spec)`; cells via `findInterceptValue(av.intercept_values, spec)` with primary fallback to `av.value`. `at_bound = true` renders the amber chip.
   - 7 new unit tests in `results-grid-columns.test.tsx` cover `resolveColumns` over all four colId shapes + `buildDrcColumns` output shape.

7. **`971c03de` — `refactor(screening): dose-response chart labels via interceptLabel`** (spec Surface #5 polish)
   - The compound detail sheet already renders the chip-stack via `<DoseResponseChart />`, but the chart's own primary line used `CURVE_TYPE_LABELS[curve.curve_type]` (which post-033 is "descriptive only") and the secondary chips had an inline `spec.label ?? KIND+LEVEL` fallback. Both replaced with `interceptLabel(spec)` — single source of truth, per-protocol relabels now visible everywhere.
   - Pre-multi-intercept curves with no persisted `intercept_values` still fall back to the legacy `CURVE_TYPE_LABELS` lookup so they keep rendering "EC50" / "IC50" as before.

8. **`c92f3d11` — `feat(screening): readout-data table denorms one column per protocol intercept`** (spec Surface #6)
   - `readout-data-table.tsx` was emitting a single italic `${rd.name} (${unit})` column per DR readout-def, sourced from `curve.fitted_value`. Multi-intercept protocols (EC50 + EC90) showed only the primary on every well row.
   - Now emits one column per declared intercept (header `${rd.name} ${interceptLabel(spec)}`, colId `${rd.id}::${kind}::${level}`, value via `findInterceptValue` with primary fallback to `curve.fitted_value`, amber chip on `at_bound`). Defensive fallback for DR readouts with no declared intercepts keeps the single anonymous column.
   - No backend change — the denorm join lives in the FE `curveLookup` and `intercept_values` was already on `CurveDetail` since Surface #2.

9. **`622490f8` — `fix(search): detail drawer Selected Protocols card missing on DR rows`**
   - Browser-smoke regression caught after Surface #4: opening a compound's detail drawer showed "Also tested in 1 other protocol" but no "Selected Protocols" section / chart, even when the grid row clearly had EC50 + EC90 + plot for that protocol.
   - Root cause: `search-page.tsx` derived `visibleProtocolIds` via `c.split(":")[1]`. That used to be the proto_id on the pre-033 `drc:<proto>:<curve_type>` token, but post-033 the token is `drc:<readout_def_id>` — `parts[1]` is a readout-def UUID, not a proto_id — so `visibleSet.has(group.protocol_id)` in `compound-detail-sheet.tsx` always fell through and every DR-tested protocol got bucketed into the collapsed "Others" group.
   - Same root cause family as the grid-grouping bug fixed in `e67b7641`. Lifted the resolver into shared `frontend/src/features/research-organization/lib/protocol-column-id.ts` (`resolveColumns`, `uniqueProtocolIds`); both `results-grid.tsx` and `search-page.tsx` now go through it. The `ReportCustomizer.activeProtocolIds` flow-through (search-page.tsx:456) gets the fix automatically. +5 unit tests for the shared helper.

10. **`c561f557` — `feat(screening): promote Intercepts to first-class in protocol design`**
    - Browser smoke surfaced a UX gap: after Surfaces #1–#6 every downstream UI emits one column per intercept, but the dialog that lets a chemist *declare* intercepts had the editor hidden inside a collapsed `<details>` labeled "Data Calculations" below "Classification thresholds".
    - **Edit dialog** (`detail-tabs/readout-definition-dialog.tsx`): InterceptsEditor moves up to sit directly between Y Layer and the Advanced X-axis disclosure (answers "what do we measure?" before "how strict are the fit bounds?"). Drops the `<details>` wrapper — always visible, labeled "Intercepts" with the inline hint `One row per intercept (EC50, EC90, IC10, …) — all derived from the same Hill fit`.
    - **Viewer dialog** (`readout-definition-viewer-dialog.tsx`): "Data Calculations" → "Intercepts", reordered above "Fit Parameters".
    - **Create dialog** (`create-protocol-dialog.tsx`): previously emitted `dose_response_config` with no `intercepts` field — new protocols always started with the implicit single 50% intercept. Added `dr_intercepts: InterceptSpec[]` to the form schema (default `[]`), rendered the editor in the DR-config block right after Curve Type / X / Y, included `intercepts` in the submit payload only when the chemist explicitly added ≥1 row (empty stays implicit, keeping the wire terse).
    - Curve Type kept as-is — post-033 it no longer carries identity (that's `readout_definition_id`) but still seeds the implicit primary intercept and picks IC-vs-EC direction; chemists read "IC50/EC50" as scientific terms, not identity tokens.

**Verification:**
- Backend: 2422 → 2438 → 456 → 2424 green at each commit (final sweep after Surface #4 wire-shape).
- Frontend: 106 → 115 → 122 → 127 tests green. `pnpm exec tsc --noEmit` clean throughout.
- Refit script ran successfully on dev DB; orval regen committed.
- Browser smoke: NOT done. Worth verifying these surfaces visually:
  - Run page → Dose-Response tab: should show EC50 + EC90 columns on `Mtb_WCA_mc2-7000_Resazurin`. 3 of 21 curves are legacy (no EC90 persisted) — those cells should render "—" with a Recompute hint.
  - Protocol page → Activity tab: per-readout intercept columns + Mean + Class + Curve sparkline.
  - Molecule detail → Activity tab: per-Card table with intercept columns matching each protocol's spec list.
  - Search results grid: per-protocol column groups with one sub-column per intercept (EC50 + EC90 on the Mtb_WCA protocol) + Plot column at the end. Legacy curves still primary-fallback to `value` (so 3 of 21 should fill EC50 but blank EC90).
  - Compound detail drawer (right-side sheet on a search row click): per-protocol DR chart shows primary intercept on its summary line + secondary intercept chips, both via `interceptLabel` (so a relabeled "Potency" / "Coverage" surfaces here too, not just on the run-DR table).
  - Readout-data page: every well row now denorms one column per intercept (e.g. "Resazurin EC50 (µM)" + "Resazurin EC90 (µM)") instead of a single anonymous fitted_value column.
  - EC90 marker fix (from 0d8aae80): toggling "EC50 marker" on a curve dialog should no longer collapse the Y axis.

**Remaining spec surfaces (in priority order):**
- **#7 Hit-criteria builder** — `hit-criteria-dialog.tsx` hardcodes "Fitted Value" as the LHS option. Extend criterion model with `intercept_key: {kind, level}`; FE dropdown lists every protocol intercept by `interceptLabel(spec)`; legacy criteria read at `kind=primary.kind, level=primary.level`. Highest scope — domain model + persistence + API + FE.
- **#8 Exports** — run export, project export, search export all need per-intercept columns (header via `interceptLabel`; optional CI low/high sub-columns when at least one row has non-null CI).
- **#9 Curve cards** — already correct (no work).

**How to resume:**
1. **Browser-smoke pass.** Six surfaces shipped this conversation (run DR table, protocol activity tab, molecule activity tab, search grid, search detail drawer, readout-data table) plus the protocol-design editor polish. Reload Cellar and walk each one against the Mtb_WCA_mc2-7000_Resazurin protocol — that's the live test case the work was built against. Two surfaces (drawer + grid grouping) had already-shipped bugs caught during smoke, so don't skip this.
2. **Push** — `prot-2` is 12 commits ahead of `e807dd03`, nothing pushed yet. If smoke is clean, push.
3. **Pick next surface.** #7 (hit-criteria builder) is highest-scope remaining — touches `HitCriterion` value object (`backend/src/cellar/domain/shared/hit_criterion.py:14`) + persistence (JSONB, no migration needed since `to_dict`/`from_dict` already round-trip), API DTOs, FE `hit-criteria-dialog.tsx`, and the campaign hit-call evaluator. Strategy: add optional `intercept_key: {kind, level} | None`; legacy criteria (null) treated as `(kind=primary.kind, level=primary.level)` at read time. #8 (exports) is a scoping pass first — no single export-builder module was found, suggests it's scattered or partial.

**Diagnostic anchors if something looks wrong:**
- `frontend/src/features/screening-assay/lib/intercept-label.ts` — only place chemist-facing intercept labels are produced or cell lookups happen.
- `frontend/src/features/research-organization/lib/protocol-column-id.ts` — only place `drc:<rd_id>` / `rd:<proto>:<rd>` colIds get joined back to their owning protocol. Both `results-grid.tsx` and `search-page.tsx` go through `resolveColumns`/`uniqueProtocolIds` here.
- Backend serialization: `application/screening/molecule_activity_service.py::_serialize_intercept_values` — single helper feeds both the molecule-activity payload and the search-grid `ActivityValue.intercept_values`.

**Open caveat:** Multi-DR protocols (a protocol declaring 2+ DOSE_RESPONSE readout-defs with their own intercept lists) still use the *first* DR readout's intercepts on every grid. Per-readout column groups are documented as a known limitation in the spec — defer until a real protocol surfaces it.

Long-lived state (architecture decisions, branch state, operational backlog) lives in `~/.claude` memory — see `MEMORY.md` for the index, especially `feedback_drc_identity.md` (the "curves keyed by readout_definition_id" principle that motivated this whole refactor).
