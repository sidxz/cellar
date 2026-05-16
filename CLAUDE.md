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
