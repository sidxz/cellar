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

**Branch:** `prot-2`, N commits ahead of `e807dd03` (use `git rev-list --count e807dd03..HEAD`) (the merged `fe2` HEAD). Browser-smoke for Surfaces #1–#7 passed 2026-05-14; commit #16 (Option A — multi-intercept channels) and commit #17 (mirror-protocol bulk-create) both need fresh smoke. Nothing pushed. Dev DB migrated to head (`035_cc_intercept_key`).

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

11. **`db04e938` — `feat(screening): hit-criteria builder targets specific dose-response intercepts`** (spec Surface #7)
    - **Domain.** `HitCriterion` (`backend/src/cellar/domain/shared/hit_criterion.py`) gains optional `intercept_key: InterceptKey | None`. New frozen VO `InterceptKey(kind, level)` adjacent to it — separate from the heavier `InterceptSpec` (which carries `basis` + `label` for protocol-design concerns); a *key* is just `(kind, level)`. `to_dict`/`from_dict` round-trip transparently; no migration since both carriers (`Protocol.recommended_hit_criteria`, `CampaignChannel.hit_threshold`) are JSONB.
    - **Evaluator.** New `_threshold_input_value(c, threshold)` helper at `application/research_organization/channel_resolution.py` resolves the right scalar per-candidate. Three aggregating selection rules (LATEST_APPROVED_RUN, MEAN_ACROSS_RUNS, GEOMETRIC_MEAN) compute an `eval_value` alongside the measurement `value` — the stored cell value stays the primary aggregate while `hit_call` honors the criterion's intended intercept. Legacy criteria (no `intercept_key`) collapse to identity. `ResolvedCandidate.intercept_values` carries the curve JSONB end-to-end; SQL projection added in both `_fetch_curve_candidates` and `fetch_candidates_for_runs`.
    - **API.** `HitCriterionDTO` (`interface/routes/_campaign_dtos.py`) mirrors the new field via a new `InterceptKeyDTO`. Orval regen propagated; FE hand-typed `HitCriterion` interface updated. Protocol routes for `recommended_hit_criteria` already serialized as `list[dict]` and round-trip via `HitCriterion.from_dict`/`to_dict`, so no route code change needed.
    - **Dialog.** New helper `screening-assay/lib/hit-criteria-options.ts` turns `protocol.readout_definitions` into a flat option list — one entry per intercept for each DR readout (`"Resazurin EC50"`, `"Resazurin EC90"`), one entry per non-DR readout, plus `Curve Class`. `hit-criteria-dialog.tsx` consumes it; `optionIdForRule` maps existing rules back to option ids (legacy unkeyed DR rules map to the primary). Saving a rule that targets a primary intercept keeps `intercept_key=null` (terse wire shape for legacy / primary) — only secondary intercepts persist an explicit `{kind, level}`.
    - **Filters.** `applyHitFilter` (run DR results) and `applyFilters` (protocol activity tab) honor `intercept_key` via `findInterceptValue`, falling back to `fitted_value` / `best` for unkeyed rules. Missing intercept on a legacy curve → row fails the criterion (same "no value, no pass" semantic). `criterionLabel` surfaces the intercept in chip text ("Resazurin EC90 < 50") via the implicit KIND+LEVEL label.
    - **Out of scope** (intentionally deferred): `deriveChannelHitDefaults` strips `intercept_key` when projecting a protocol recommendation onto a campaign channel's hit-threshold form. The channel UI doesn't yet model an intercept selector. Follow-on for channel-popover.tsx.

12. **`dbc42464` — `feat(search): unified Export menu — Excel + CSV + SDF in one dropdown`** (spec Surface #8 — scope-reduced)
    - Surface #8 originally called for per-intercept value columns *and* companion CI low / CI high sub-columns on every export. Per-intercept value columns already flow into AG Grid's CSV/Excel via `getAllDisplayedColumns()` (Surfaces #1, #4 made grids dynamic), so the run / activity / readout-data exports already produce per-intercept columns out-of-the-box. **CI sub-columns vetoed at smoke** — a 2-intercept protocol balloons the run DR grid to `EC50 | EC50 CI low | EC50 CI high | EC90 | EC90 CI low | EC90 CI high | R² | …` with truncated headers. Captured in [[feedback-no-ci-subcolumns]]; chemists read CI on the curve card chip, not inline columns.
    - **Search export wiring** was the actual gap on this surface — the search `ResultsGrid` had no Export button at all. `ResultsToolbar` had a chemistry-only "Export" button that triggered SDF download; everything else was missing. Refactored to a single Export dropdown so chemists get *one* Export affordance with three formats (Excel/CSV/SDF). Shared `ExportToolbar` gains an `extraItems` prop, `DataGrid` plumbs it through, search `ResultsGrid` consumes an optional `onExportSdf` callback and emits the SDF entry alongside Excel + CSV. `ResultsToolbar`'s standalone SDF button + `onExport` prop dropped.
    - 5 files / +71 / −10 total; no backend touched. `pnpm exec tsc --noEmit` clean, 138 FE tests green, no new tests added (the new `extraItems` prop is a straight pass-through; behavioral verification is the browser smoke).

17. **`00cf02bd` — `feat(campaign): mirror protocol — bulk-create channels for every readout`** (chemist shortcut on top of #16)
    - **Why now.** With Option A, every protocol readout's identity is fully expressible at the channel layer (readout_def + normalization + intercept_key). That makes "mirror this protocol's whole readout structure into one channel each" a one-shot operation — no longer needs the chemist to walk add-from-runs (which requires picking specific runs first) or click through `+ Channel` N times.
    - **Use case** (`application/research_organization/mirror_protocol_channels.py`): iterates protocol.readout_definitions; per-readout decision tree is small and explicit — DR with declared intercepts emits one channel per intercept (primary stores `intercept_key=None`, secondaries store `{kind, level}`); DR with no declared intercepts emits one channel for the implicit primary; non-DR emits one channel sourced from `readout_data` with the readout's primary normalization layer (matches channel-popover's create-mode auto-pick).
    - **Idempotency.** Existing channels with a matching `(protocol_id, readout_definition_id, normalization_applied, intercept_key)` key are silently skipped. Chemist can re-mirror after editing the protocol's intercepts without duplicating columns. Returns `{channels_created, channels_skipped}` so the FE toast can be precise ("Created 3 channels (2 already existed)" vs "No new channels — 5 already mirrored").
    - **Hit-threshold carry-forward.** `_match_recommended_threshold(recommended, readout_name, intercept_key)` prefers an exact `(name, intercept_key)` match. Falls back to a same-readout-name criterion only when the channel targets the primary intercept — non-primary channels without an exact match get no auto-threshold (avoids surfacing the wrong number as a hit criterion). Mirrors the same matching rule that Option A introduced for `AddCampaignChannel`'s carry-forward.
    - **Label dedupe.** Same rule as add-from-runs (commit #15) and `interceptLabel(spec)`: rd.name === primary intercept's label → drop the redundant prefix. So a CDD-style protocol with `rd.name = "EC50"` mirrors as channels labelled `"EC50"` / `"EC90"` (not `"EC50 EC50"` / `"EC50 EC90"`); a protocol with `rd.name = "Resazurin"` mirrors as `"Resazurin EC50"` / `"Resazurin EC90"`.
    - **Wire.** New `POST /api/v1/campaigns/{id}/channels/mirror-protocol` with `MirrorProtocolRequest{protocol_id}`, returns `MirrorProtocolOutcomeResponse{channels_created, channels_skipped, campaign}`. Single-channel `AddCampaignChannel` route stays the authoritative path for one-at-a-time creation.
    - **DI / dependencies.** `MirrorProtocolChannels` registered in `infrastructure/di/_research_organization.py` (uses the same `ChannelResolver` + `EventDispatcher` as the single-channel use case); `MirrorProtocolChannelsDep` annotation in `interface/dependencies/_research_organization.py`.
    - **FE component** (`screen-campaign/components/sections/channels-section.tsx::MirrorProtocolPopover`): new pill `[Copy] Mirror protocol` placed next to `[+ Channel]` in the Channels section header. Picks a protocol from `useProtocolSummaries([projectId])`, fires the mutation, on success shows a count-aware toast (created vs already-mirrored) and invalidates `campaignKeys.detail`. Both popovers also gain `max-h: var(--radix-popover-content-available-height) overflow-y-auto` since the channel-popover form can be tall on multi-intercept readouts.
    - **Tests.** 6 new unit tests in `test_mirror_protocol_channels.py` cover: multi-intercept DR split + recommended threshold pickup, idempotent re-mirror, non-DR with primary normalization, draft-only guard (CLOSED campaign rejected), protocol-not-found, CDD-style label dedupe.
    - 11 files / +993 / −19. 217 BE research_org tests green (211 → 217 = +6 mirror tests). 152 FE tests, `pnpm exec tsc --noEmit` clean.

16. **`1c19f594` — `feat(campaign): channel intercept_key as top-level field (Option A)`** (commits #13–#15 architectural fix)
    - **The chemist's workflow.** Protocol declares two intercepts on its Resazurin readout (EC50 + EC90). Add-from-runs creates two channels: EC50 with `use_for_filter: ON` + `< 50` threshold; EC90 with `use_for_filter: OFF` + **no threshold** (display-only column). Pre-Option-A: EC90 channel collapsed onto EC50's `channel_key` (identity was carried inside `hit_threshold.intercept_key`, which is `null` when there's no threshold); preview showed 22 mols / **0 hits** + identical cell values for both channels. Option A: 22 mols / **2 hits** + distinct EC50/EC90 numbers per row.
    - **Root cause.** Pre-Option-A: channel identity lived inside `HitCriterion.intercept_key` (= the threshold). A channel without a threshold lost its intercept identity before leaving the FE. Post-Option-A: identity lives at the top level of `CampaignChannel` / `ChannelImportConfig`. `HitCriterion.intercept_key` is preserved for protocol-level `recommended_hit_criteria` evaluation and as the source-of-truth when carrying a criterion forward via `deriveChannelHitDefaults`, but the channel's own `intercept_key` is authoritative for cell value + hit decision.
    - **Domain.** `CampaignChannel.intercept_key: InterceptKey | None` (`backend/src/cellar/domain/research_organization/campaign_channel.py`). Field is set at creation; chemist wanting a different intercept creates a new channel (matches `readout_definition_id` lifecycle).
    - **Persistence.** Migration `035_cc_intercept_key` — additive JSONB column on `campaign_channel`. NULL on backfill (matches today's "primary" semantic). Repo `_channel_to_domain` / `_channel_to_model` / `_channel_update_model` serialize via `InterceptKey.from_dict` / `to_dict`. Dev DB migrated.
    - **Resolver.** New `_intercept_scalar(c, intercept_key) -> float | None` (`channel_resolution.py`) is the single source of truth for "value at this intercept on this candidate." `_threshold_input_value(c, threshold)` becomes a thin shim that composes it (kept for protocol-level criterion paths). `ChannelResolver.resolve()` reads `channel.intercept_key` for the cell value across all three selection rules — `value` and `eval_value` collapsed into one field (the channel's value IS what gets compared against the threshold). Missing intercept on the curve (legacy fit, or intercept added post-fit) → ND cell, not a primary-fallback.
    - **Application.** `ChannelImportConfig.intercept_key` + `AddCampaignChannelCommand.intercept_key`. `preview_run_import._channel_key`, `existing_by_key`, and `add_results_from_runs.existing_by_key` switch their fourth tuple element from `cfg.hit_threshold.intercept_key` to top-level `cfg.intercept_key`. `_apply_selection_rule(rule, intercept_key)` operates on a key, not a threshold (cleaner signature). Protocol carry-forward in `AddCampaignChannel` now prefers a `recommended_hit_criteria` entry that matches **both** readout name AND intercept_key — an EC90-targeting channel picks up the protocol's EC90 criterion, not its EC50.
    - **DTOs.** `AddChannelRequest.intercept_key: InterceptKeyDTO | None`, `CampaignChannelResponse.intercept_key`, `ChannelImportConfigDTO.intercept_key`. `UpdateChannelRequest` unchanged (intercept identity is set-on-create).
    - **FE channel-popover** (`channel-popover.tsx`): `addMutation.mutate` payload gains `intercept_key: computeInterceptKey()` at the top level (parallel to `normalization_applied`); the existing nested `hit_threshold.intercept_key` stays as informational/legacy and is identical when both fields are populated. Edit-mode hydration prefers `existing.intercept_key` (post-Option-A) with a fallback to `existing.hit_threshold.intercept_key` (legacy).
    - **FE add-from-runs** (`add-from-runs-dialog.tsx::buildPayload`): emits `intercept_key` as a top-level field on each `channel_configs[]` entry. The existing `c.intercept_key` field on `ChannelConfigUI` (added in commit #14) was already shaped correctly — this commit just unbinds it from the nested `hit_threshold`.
    - **FE channels-section** (`sections/channels-section.tsx::formatThreshold`): now takes the full channel (not just the threshold). Prefers `channel.intercept_key` over the threshold's; legacy rows fall back to threshold's. Chip text unchanged ("hit if EC90 < 50") for non-primary, primary stays implicit.
    - **FE narrowing** (`screening-assay/lib/intercept-label.ts::narrowInterceptKey`): new helper narrows the orval-generated `{kind: string, level: number}` to the hand-typed `InterceptKey` ({"ec" | "ic"} discriminator). Used at the wire→domain boundary in channel-popover + channels-section.
    - **Tests.** Backend: 4 resolver tests updated to the new shape (intercept identity on channel, not threshold) + 1 new preview test (`test_multi_intercept_channels_with_display_only_second_intercept`) — chemist's actual workflow, two molecules with EC50 < 50, EC50 channel has threshold, EC90 channel has NONE, both molecules hit, cells show intercept-specific values. Existing `test_multi_intercept_channels_disambiguate_cells_and_hits` updated to set `intercept_key` top-level on the configs. 2454 backend tests green (+2 from baseline 2452). 152 FE tests green, `pnpm exec tsc --noEmit` clean.
    - **Open question handling.** Per the brief: (1) `HitCriterion.intercept_key` stays — still needed for protocol-level criteria; (2) migration backfill = NULL (read-side fall-through on FE for legacy rows); (3) channels-same-readout-different-intercepts disambiguate by ik tuple naturally; (4) channel `label` storage stays at-save (the chemist's named entity is the channel); (5) CDD-style readout names (`rd.name === "EC50"`) — label dedupe from #15 still works; (6) at runtime, channel's intercept wins over threshold's.

15. **`e364c07b` — `fix(campaign): multi-intercept channels — proper cells, hits, labels`** (commit #14 hardening)
    - **The smoke gap.** Live test of #14 on `Mtb_WCA_mc2-7000_Resazurin` (EC50 + EC90 readout) reproduced as: preview showed 22 molecules / **0 hits** while individual rows had HIT badges. Three coordinated bugs:
    - **(a) Channel-key collision (backend, preview + mutation).** Both `preview_run_import.py` and `add_results_from_runs.py` keyed channels by `(protocol, readout, normalization)`. Multi-intercept channels (EC50 + EC90 on the same readout) collapsed onto one key. In preview's hit aggregation, the EC50 and EC90 cells both got bucketed as "active" — the EC90 cell's `None` hit_call (no threshold) dragged the `all()` check to False, killing the aggregate. Fixed by extending the key tuple with `intercept_key` as a fourth element. Both `existing_by_key` (reuse lookup) and the cell-bucket key now disambiguate per intercept.
    - **(b) Display value + hit_call used primary aggregate (backend).** `_apply_selection_rule` returned `_Picked.value` = primary fitted aggregate. Cell display and `_compute_hit_call` both keyed off this — so an EC90-targeting channel showed the EC50 number and evaluated the threshold against EC50. Fixed by extending `_Picked` with `eval_value` (intercept-aware aggregate computed via `_threshold_input_value`). For MEAN / GEOMETRIC rules, `eval_value` aggregates the per-candidate intercept-specific values (not the lookup on the primary aggregate). Both `value` and `hit_call` paths use `eval_value`; the persisted `CampaignMeasurement.value` also stores the intercept's scalar — so the cell IS the intercept the channel targets.
    - **(c) FE label collision.** Add-from-runs' `${rd.name} ${interceptLabel(spec)}` produced "EC50 EC50" / "EC50 EC90" when `rd.name` matched the primary intercept's label (CDD-style readout naming). Detect & drop the redundant prefix → "EC50" / "EC90". Distinct rd names (e.g. "Resazurin") keep full prefix.
    - 4 files (`preview_run_import.py`, `add_results_from_runs.py`, `add-from-runs-dialog.tsx`, `test_preview_run_import.py`); +268 / -25. New backend test `test_multi_intercept_channels_disambiguate_cells_and_hits` walks a full 2-channel scenario: mol_a (EC50=4, EC90=40) hits both, mol_b (EC50=10, EC90=200) hits EC50 only. 233 BE tests (+1), 152 FE tests, tsc clean.

14. **`0003597e` — `feat(campaign): add-from-runs splits multi-intercept DR readouts per intercept`** (commit #13 follow-on)
    - **The gap.** Browser smoke on commit #13 surfaced a structural issue: a protocol declaring EC50 + EC90 on its Resazurin readout still imported as ONE channel into the campaign (targeting the primary, EC50). EC90 values went unsurfaced in the campaign grid even though they were computed and persisted on every curve. Commit #13 made the *single channel* intercept-aware; this commit makes the *import flow* surface every intercept as its own channel.
    - **`add-from-runs-dialog`.** `channelConfigs` now `flatMap`s DR readouts with ≥2 declared intercepts into N configs. Each channel is labelled `${rd.name} ${interceptLabel(spec)}` (e.g. "Resazurin EC50" / "Resazurin EC90"), carries the correct `intercept_key` (primary → null per Surface #7 convention; secondary → explicit `{kind, level}`), and pulls its own hit threshold via a per-intercept-filtered `deriveChannelHitDefaults` call. Single-intercept DR readouts and non-DR readouts keep the legacy one-channel-per-readout path (with `interceptKey = undefined` so pre-Surface-#7 criteria without `intercept_key` still match — backwards-compat is preserved).
    - **`deriveChannelHitDefaults` signature.** New optional `interceptKey?: InterceptKey | null` arg. `undefined` = no filter (legacy behavior); `null` = filter to primary-targeting criteria (`intercept_key` null or missing); `{kind, level}` = exact-match filter. Curve-class criteria are NOT filtered — they apply per-readout. The channel-popover caller still passes nothing (legacy behavior preserved — chemist's single-add path doesn't need per-intercept criterion auto-fill).
    - **`channelConfigKey` helper.** `userEditedConfigs` was keyed by `rd.id`, which collides when one rd emits N channels. New `channelConfigKey(rd_id, intercept_key)` returns `rd_id` for primary / non-DR / single-intercept channels (back-compat with the existing key shape), `${rd_id}:${kind}:${level}` for secondaries. So a chemist's edit to the EC90 row doesn't clobber the EC50 row's saved state.
    - **Hook swap.** `useGetProtocolApiV1ProtocolsProtocolIdGet` (orval, types `dose_response_config` as loose `Record<string, unknown>`) → hand-typed `useProtocol` from `screening-assay/hooks/use-protocols`. Same endpoint, stronger types so `intercepts` resolves as `InterceptSpec[]` rather than `{}`.
    - 3 files / +217 / −53. 5 new tests (`hit-criteria-defaults.test.ts`) for filter behavior. 147 → 152 tests green, `pnpm exec tsc --noEmit` clean.

13. **`73bb6f07` — `feat(campaign): channel hit threshold honors intercept_key end-to-end`** (Surface #7 follow-on)
    - **Domain & wire.** Backend round-trip already established by Surface #7 — `AddChannelRequestHitThreshold = HitCriterionDTO | null` carries `intercept_key`. FE was the only layer dropping the field.
    - **Defaults helper.** `ChannelHitDefaults` (`hit-criteria-defaults.ts`) gains `intercept_key: InterceptKey | null`. `deriveChannelHitDefaults` preserves it from the matching criterion. Pairing two criteria into `between` now requires their intercept_keys to match — `EC50 > 5 AND EC90 < 50` no longer collapses into a nonsensical `between [5, 50]` range (falls back to first criterion). Treats undefined / null as equal (= primary) for legacy mixed-pre/post-Surface-#7 criterion data.
    - **Channel popover form.** New `hit_intercept_key` schema field (stringified `${kind}:${level}` id). `parseHitThreshold` extracts the persisted key defensively (legacy channels with no field → null; primary channels with explicit null → null; non-primary → `{kind, level}`). Two useEffects keep the picker resolved: the existing create-mode `deriveChannelHitDefaults` effect now also `setValue`s the intercept; a new edit-mode effect fills from `existing.hit_threshold.intercept_key` once `fullProtocol` resolves (falls back to the readout's primary). Save logic: primary intercept → `intercept_key: null` (terse, tracks protocol's current primary if intercepts are later reordered); non-primary → explicit `{kind, level}`; non-DR channels → null regardless.
    - **Picker UI.** Small `<Select>` inline with the operator dropdown — one entry per declared intercept, labelled via `interceptLabel(spec)` (respects protocol-defined custom labels), primary tagged `(primary)`. Visible only when `source_kind === "dose_response_curve"` AND `readout.data_type === "dose_response"` AND `intercepts.length >= 2`. Hidden when the threshold operator is `"none"` since there's nothing to compare. Caption updates: `Hit if Resazurin EC90 < 50 uM`.
    - **Display.** `channels-section.tsx::formatThreshold` surfaces the intercept in the chip when non-null — `hit if EC90 < 50` for non-primary, `hit if < 50` for primary (primary is implicit, every channel has one — naming it everywhere is noise). Uses the canonical `interceptKeyLabel(key)` since the channels-section doesn't have full `InterceptSpec` context (no protocol-side custom label).
    - **Add-from-runs dialog.** `ChannelConfigUI` gains `intercept_key: InterceptKey | null` — auto-populated from `deriveChannelHitDefaults` for DR readouts, null for non-DR. `buildPayload` includes it in the persisted `hit_threshold`. No inline picker in this dialog (multi-row config table; chemist refines via channel popover after creation).
    - **Helpers** (`intercept-label.ts`): `interceptKeyLabel(key)` for key→canonical-string, `interceptKeyId(key) / parseInterceptKeyId(id)` for form-value round-trip.
    - 7 files / +392 / −20 total, no backend touched. `pnpm exec tsc --noEmit` clean, 138 → 147 FE tests green (9 new: 4 helpers + 5 carry-forward including mismatched-keys-don't-pair + null/undefined equivalence).

**Verification:**
- Backend: full unit + integration sweep at HEAD (post-#16 + #17) = **2269 passed** (research_org subset = 217, of which 6 are new mirror tests). Commit #16 added `test_multi_intercept_channels_with_display_only_second_intercept` and updated 4 existing resolver tests; commit #17 added 6 mirror-use-case tests. No domain layer breakage. Migration 035 applied to dev DB.
- Frontend: 152 tests green throughout (no new FE tests in #16 — wire-shape changes covered by backend; no new FE tests in #17 — the popover is stateless React behind the orval-generated mutation hook, smoke-only). `pnpm exec tsc --noEmit` clean.
- Refit script ran successfully on dev DB; orval regen committed.
- **Browser smoke: PASSED on 2026-05-14** against the live `Mtb_WCA_mc2-7000_Resazurin` protocol — Surfaces #1–#7 walk cleanly. Commits #12 (unified Export menu), #14, #15, **#16 (Option A)**, **#17 (mirror-protocol)** still need fresh browser smokes.

**Remaining spec surfaces:**
- **#8 Exports** — *effectively done.* Per-intercept columns already inherit from the grid; CI sub-columns intentionally dropped (see [[feedback-no-ci-subcolumns]]); search export button shipped as a unified Excel/CSV/SDF dropdown in commit #12. Needs browser smoke before claiming closed.
- **#9 Curve cards** — already correct (no work).
- **Channel-popover hit-threshold carry-forward** (Surface #7 follow-on) — **done in commit #13.** Both creation paths (channel popover + add-from-runs dialog) thread `intercept_key` end-to-end; display chip surfaces non-primary intercepts.
- **Per-intercept channel split on import** (commit #13 follow-on) — **done in commit #14.**
- **Channel-key collision + display-only multi-intercept channels** (commit #14 hardening) — **DONE in commit #16 (Option A).** `intercept_key` is now a top-level field on `CampaignChannel` / `ChannelImportConfig` / `AddChannelRequest`, decoupled from `hit_threshold`. A display-only EC90 channel (no threshold) now keeps its intercept identity end-to-end. Migration 035 (`campaign_channel.intercept_key` JSONB NULL, additive, NULL on backfill). The brief at `docs/superpowers/specs/2026-05-14-multi-intercept-channels-handoff.md` is the closed reference for what was shipped.
- **Bulk-create channels mirroring a protocol** (chemist shortcut on top of #16) — **DONE in commit #17.** `MirrorProtocolChannels` use case + `POST /channels/mirror-protocol` route + `MirrorProtocolPopover` next to `+ Channel` in channels-section. Idempotent re-mirror, multi-intercept DR readouts emit one channel per intercept, hit-threshold carry-forward matches `(readout_name, intercept_key)`.

**How to resume:**
1. **Live smoke commit #16** on the `Mtb_WCA_mc2-7000_Resazurin` protocol against a fresh campaign:
   - "Add from runs" → pick protocol → select May 12 2026 run (22 mols) → configure: EC50 channel `use_for_filter: ON`, `< 50 µM`; EC90 channel `use_for_filter: OFF`, **no threshold**; RSZ (% Inhibition) `use_for_filter: OFF`, no threshold.
   - Click Preview. Expected: `22 molecules · 2 hits · 20 non-hits`. CV-00967 (EC50=4.68, EC90~40) and CV-00983 (EC50=13.7, EC90~?) are the hits.
   - Per-compound cells: EC50 column shows EC50 numbers, EC90 column shows distinct EC90 numbers — not the same number. RSZ column shows % inhibition.
   - HIT badges only on EC50 cells of CV-00967 + CV-00983; EC90/RSZ cells blank/no-decision.
   - Click "Add 2 hits" → campaign persists. DB inspection on `campaign_channel`: 2+ rows for the Resazurin readout — EC50 row has `intercept_key = NULL`, EC90 row has `intercept_key = {"kind": "ec", "level": 90.0}`.
   - Edit the EC90 channel via channel-popover, set a threshold `< 100`. Re-render. EC90 cells now show HIT badges for compounds with EC90 < 100. Hit aggregate updates.
2. **Live smoke commit #17** on the same `Mtb_WCA_mc2-7000_Resazurin` protocol against a *fresh* campaign with NO channels:
   - Open the campaign → click `[Copy] Mirror protocol` pill in Channels section header → pick `Mtb_WCA_mc2-7000_Resazurin` → click **Mirror**.
   - Expected toast: `Created N channels` where N matches the protocol's readouts (DR with EC50+EC90 = 2 channels; non-DR = 1 each). Channels appear in the section list with correct labels.
   - Click `Mirror protocol` again with the same protocol: expected toast `No new channels — N already mirrored`. No duplicates appear.
   - DB inspection on `campaign_channel`: rows match expected shape — EC50 row has `intercept_key = NULL`, EC90 row has `intercept_key = {"kind": "ec", "level": 90.0}`, non-DR rows have `intercept_key = NULL` and `normalization_applied` set to a computed layer (e.g. `"percent_inhibition"`).
3. **Smoke commits #12 (unified Export menu) + #14 (add-from-runs split) + #15 (channel-key collision)** if not already done — independent of Option A / Mirror, safe to ship.
4. **Push** — `prot-2` is N commits ahead of `e807dd03` (use `git rev-list --count e807dd03..HEAD`), nothing pushed. After all live smokes pass, push the branch and open a PR against `main`.

**Diagnostic anchors if something looks wrong:**
- `frontend/src/features/screening-assay/lib/intercept-label.ts` — only place chemist-facing intercept labels are produced or cell lookups happen. After commit #16: `narrowInterceptKey` is the wire→domain narrower used wherever orval-generated `{kind: string, ...}` meets the hand-typed `InterceptKey`.
- `frontend/src/features/screening-assay/lib/hit-criteria-options.ts` — only place the hit-criteria dialog's option list is built or a rule is mapped back to an option id.
- `frontend/src/features/research-organization/lib/protocol-column-id.ts` — only place `drc:<rd_id>` / `rd:<proto>:<rd>` colIds get joined back to their owning protocol. Both `results-grid.tsx` and `search-page.tsx` go through `resolveColumns`/`uniqueProtocolIds` here.
- Backend serialization: `application/screening/molecule_activity_service.py::_serialize_intercept_values` — single helper feeds both the molecule-activity payload and the search-grid `ActivityValue.intercept_values`.
- Backend resolver: `application/research_organization/channel_resolution.py::_intercept_scalar` — single helper produces the channel's per-candidate scalar from `channel.intercept_key`. `_threshold_input_value` is now a thin shim that composes `_intercept_scalar` with `threshold.intercept_key` (kept for protocol-level criterion evaluation paths). `ChannelResolver.resolve` reads `channel.intercept_key` for the cell value across all three selection rules.
- Backend channel-key: `application/research_organization/preview_run_import.py` + `add_results_from_runs.py` — the fourth tuple element of the channel-reuse key is `cfg.intercept_key` (top-level), not `cfg.hit_threshold.intercept_key`. A display-only multi-intercept channel keeps its identity even with `hit_threshold=None`.
- Backend mirror: `application/research_organization/mirror_protocol_channels.py` — only place that bulk-creates channels from a protocol's readouts. The same idempotency key tuple `(protocol_id, readout_definition_id, normalization_applied, intercept_key)` lives here as in preview_run_import; if the FE ever calls Mirror on a protocol the chemist already added-from-runs, the matching channels skip silently.

**Open caveat:** Multi-DR protocols (a protocol declaring 2+ DOSE_RESPONSE readout-defs with their own intercept lists) still use the *first* DR readout's intercepts on every grid. Per-readout column groups are documented as a known limitation in the spec — defer until a real protocol surfaces it.

**Open follow-up: Campaign curve-expand DRY** — the campaign post-close grid's expand dialog renders via `<DoseResponseFigure>` + a custom header, while protocol-runs and search use `<DoseResponseChart isInteractive={false}>`. Different look, same data. Current-session bandaid in `curve-expand-dialog.tsx` replaced a hardcoded "IC50" with a `channelLabel`-derived label so the wrong abbreviation stops shipping; full unification (snapshot carries `curve_type` + `intercept_values` + CI + warnings; dialog renders via `DoseResponseChart` with a snapshot→DoseResponseCurve adapter) is its own task with a backfill script for already-imported campaigns. **Brief:** `docs/superpowers/specs/2026-05-14-campaign-curve-expand-dry-handoff.md` — has per-file anchors, recommended path (Option A), three rejected alternatives, and a verification scenario.

Long-lived state (architecture decisions, branch state, operational backlog) lives in `~/.claude` memory — see `MEMORY.md` for the index, especially `feedback_drc_identity.md` (the "curves keyed by readout_definition_id" principle that motivated this whole refactor).
