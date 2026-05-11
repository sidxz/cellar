# Screen-Campaign B-gap UX — Design Spec

**Status:** Brainstorming approved 2026-05-11. Implementation plan via `writing-plans`.
**Date:** 2026-05-11
**Branch:** `fe2`
**Bounded context:** `research_organization` (BC #05) — Campaign aggregate
**Builds on:** `docs/superpowers/specs/2026-05-10-screen-campaign-design.md`
**Backlog:** `docs/backlog/screen-campaign-followups.md` — "Deeper gap analysis" section

---

## 1. Purpose & framing

A `Campaign` is the screener's **final report** — the immutable artifact published to DAIKON. The original spec landed the lifecycle, persistence, and contract; the build-phase UX is crude. This spec addresses the screener-experience gaps catalogued as **section B** in the backlog:

- B1 — structure thumbnails (chemists work by sight)
- B5 — decision-count chip filter row (the report's storyline)
- B6 — multi-run import with hit-criteria preview (the curation path)
- B7 — ND/excluded qualifier gating in the override modal
- B8 — override reason field (audit defensibility)

The grade is **report**, not scratchpad: every cell must be defensible to a colleague/auditor without re-querying source data. The flexibility lives during *preview/adjustment* — snappy criterion edits, live re-filter, iterate freely. Once committed, the artifact is curated.

### 1.1. Out of scope (this session)
B2 (DR curve preview), B3 (bulk decision), B4 (bulk remove), B9 (CSV export), B10 (staleness signal), B11 (sources card on drafts), B12 (workspace-wide list), B13 (per-row audit history) — each gets its own spec.

---

## 2. Architecture overview

Three layers, all DRY against existing chem-vault machinery:

**Backend:**
- New use case: `preview_run_import.py` (read-only query, no mutation).
- Replace: `add_results_from_run.py` → `add_results_from_runs.py` (multi-run; single-run is `run_ids=[one]`).
- Migration 028: extend `campaign_measurement` with snapshot + audit columns (all nullable).
- Relax: `CampaignMeasurement.__post_init__` for `nd`/`excluded` qualifiers.
- Extend: `OverrideResultCellCommand` with `reason: str | None`.
- Extend: `get_published_campaign.py` measurement serializer for new fields.

**Frontend:**
- New `<AddFromRunsDialog>` (2-step: Configure → Preview).
- Wire it into the "Add compounds" dropdown in `compound-list-pane.tsx` (replaces the currently-disabled "From a protocol run" item).
- New `<MoleculeThumbnail>` shared component.
- New `<CampaignFilterBar>` above the results grid.
- Override modal: qualifier gating + required reason.
- "Preview as published" button + modal in builder header (bonus).

**DRY targets (no new logic written):**
- `_compute_hit_call(value, threshold)` — `application/research_organization/channel_resolution.py:99-118`. Pure function; reused by both preview and add.
- Existing channel resolver — value selection per `selection_rule`.
- `RunRepository.find_by_ids` (add bulk method if missing), `ReadoutDataRepository.find_aggregated_by_molecules`, `DoseResponseCurveRepository.find_by_run`.
- `_serialize_*` helpers in `get_published_campaign.py` — for "Preview as published".
- AG Grid Community external-filter callback API — for the chip filter.

---

## 3. B6 — Multi-run import with hit-criteria preview

### 3.1. Dialog flow — 2 steps

**Step 1 — Configure.** One scrolling form, two sections.

*Top — Run picker:*
- Search input + filter chips: `Same project`, `Approved only`, `QC pass`.
- Defaults: same project + approved + QC pass enabled.
- Scrollable checkbox list of eligible runs. Each row: run name · protocol · approval chip · run date · molecule count · Z' chip · QC chip.
- Toggles: `Show all projects`, `Show unapproved`, `Show QC failures` (default OFF).

*Bottom — Channel configuration:*
- Populated dynamically from the union of `(protocol_id, readout_definition_id)` across selected runs.
- One card per readout group:
  - Label (default = readout name; editable).
  - Selection rule radio: `latest_approved_run` (default) | `mean_across_runs` | `geometric_mean`.
  - Hit criterion: prefilled from protocol's `hit_criteria`; editable; `Use for filter ✓` checkbox (default ON if criterion present, OFF if absent).
  - Reuse indicator: "Existing channel reused" if `(protocol_id, readout_def_id)` already on campaign; else "Will create new channel".
- Global toggles:
  - Filter mode: `Hit per ALL criteria` (default — discipline) | `Hit per ANY criteria` (exploratory).
  - Commit scope: `Add only hits ✓` (default when ≥1 criterion is `Use ✓`) | `Add all compounds`.
  - Default decision: `Selected` (when scope = hits-only) | `Deferred` (when scope = all).
  - `Refresh non-override cells for already-in-campaign molecules` (default OFF).

**Step 2 — Preview.** Fires `POST /campaigns/{id}/preview-run-import` on every config change (debounced ~300 ms).

- Top chips: `Total: N` `Hits: N` `Non-hits: N` `Already in campaign: N`.
- Scrollable table; each row:
  - Structure thumbnail (48×36)
  - Reg-id + molecule name
  - Per-channel cell: `value qualifier @ concentration · N=rep_count · QC chip · hit chip`
  - Hover popover: full provenance (contributing runs, run picked by selection rule, Z' per run, override flag).
  - Greyed if `already_in_campaign = true` with an explicit tag.
- "← Back to configure" button (preserves all step-1 state) + commit button with live label: `Add 23 hits` / `Add 87 compounds`.

### 3.2. Backend contracts

#### `PreviewRunImportQuery` (read-only)

```python
@dataclass(frozen=True, kw_only=True)
class ChannelImportConfig:
    protocol_id: UUID
    readout_definition_id: UUID
    label: str
    selection_rule: SelectionRule
    hit_threshold: HitCriterion | None
    use_for_filter: bool

@dataclass(frozen=True, kw_only=True)
class PreviewRunImportQuery(Command):
    workspace_id: UUID
    campaign_id: UUID
    run_ids: list[UUID]
    channel_configs: list[ChannelImportConfig]
    filter_mode: Literal["any", "all"] = "all"  # default = AND
```

#### `PreviewRunImportResponse`

```json
{
  "summary": {
    "runs": 2,
    "channels_new": 2,
    "channels_reused": 0,
    "molecules_total": 87,
    "hits": 23,
    "non_hits": 64,
    "molecules_already_in_campaign": 4
  },
  "channels": [
    {
      "channel_key": "<protocol_id>/<readout_id>",
      "label": "IC50",
      "source": "new",
      "reuse_of_channel_id": null,
      "selection_rule": "latest_approved_run",
      "hit_threshold": {"readout_name": "IC50", "operator": "lt", "value": 1000.0},
      "use_for_filter": true
    }
  ],
  "rows": [
    {
      "molecule": {"id": "...", "registration_number": "CVT-0142", "name": "...", "smiles": "..."},
      "is_hit": true,
      "already_in_campaign": false,
      "cells": [
        {
          "channel_key": "<protocol_id>/<readout_id>",
          "value": 42.0,
          "value_qualifier": "=",
          "unit": "nM",
          "test_concentration_value": 10.0,
          "test_concentration_unit": "uM",
          "replicate_count": 3,
          "qc_pass": true,
          "hit_call": "hit",
          "source_run_id": "...",
          "source_run_name": "Run-2026-04-15",
          "source_run_date": "2026-04-15",
          "contributing_run_ids": ["...", "...", "..."]
        }
      ]
    }
  ]
}
```

#### `AddFromRunsCommand`

```python
@dataclass(frozen=True, kw_only=True)
class AddFromRunsCommand(Command):
    workspace_id: UUID
    campaign_id: UUID
    run_ids: list[UUID]
    channel_configs: list[ChannelImportConfig]
    filter_mode: Literal["any", "all"] = "all"
    scope: Literal["hits_only", "all"] = "hits_only"
    default_decision: CampaignDecision = CampaignDecision.SELECTED
    description: str | None = None
    refresh_existing_cells: bool = False
```

Flow inside one UoW:
1. Load campaign; DRAFT guard.
2. For each `ChannelImportConfig`: lookup `(protocol_id, readout_def_id)` on campaign. If exists, reuse channel id (and apply updated `selection_rule`/`hit_threshold` if user changed it). If not, `campaign.add_channel(...)`.
3. Pull aggregated readout/curve data via existing repos.
4. For each (molecule, channel): compute cell value via existing channel resolver → `_compute_hit_call(value, threshold)` (one path, identical to preview).
5. Apply `filter_mode` to compute `is_hit` per molecule across `use_for_filter=True` channels.
6. If `scope == "hits_only"`: drop non-hits.
7. For new molecules: `CampaignResult.create(..., decision=default_decision, added_from=RunRef(run_id=<first contributing>, description))`.
8. For already-in-campaign molecules + `refresh_existing_cells=True`: update non-override `CampaignMeasurement` cells (preserve measurement id — matches the `RefreshFromSources` pattern, avoids the non-deferrable `uq_campaign_measurement_result_channel` collision).
9. Snapshot all new B6-introduced fields into the measurement: `test_concentration_value/unit`, `replicate_count`, `qc_pass`, `contributing_run_ids`.
10. Dispatch events. Return `AddResultsOutcomeResponse{added, skipped, channels_created, channels_reused, campaign}`.

#### New routes

```
POST /api/v1/campaigns/{id}/preview-run-import  → PreviewRunImportResponse
POST /api/v1/campaigns/{id}/add-from-runs       → AddResultsOutcomeResponse
```

**Deprecate** (clean removal, no shim): `POST /api/v1/campaigns/{id}/add-from-run` + `add_results_from_run.py` + `AddResultsFromRunCommand`. The disabled FE dropdown item never wired a live caller.

### 3.3. Edge cases (must handle)

| Case | Behavior |
|---|---|
| Run with no data for some molecules | (compound, channel) cell = `nd`; molecule still passes filter under ANY if hits elsewhere; fails under ALL |
| No `hit_criterion` on protocol for a readout | `Use ✓` defaults off; cell shows value with no hit-call |
| `mode=hits_only` with zero hits | Commit button disabled with tooltip |
| Campaign not DRAFT | 423 from lock guard (`CampaignLockGuard`) |
| Duplicate molecules across selected runs | Idempotent dedup at molecule level; cell follows `selection_rule` |
| Already-in-campaign with `refresh_existing_cells=False` | Greyed in preview; cells untouched on commit |
| Replicate count where N=1 | No badge shown; N>1 surfaces as `N=3` chip |
| QC fail in source run | Red chip in run picker + preview cell; filter excludes by default |
| All `Use ✓` toggles disabled | No active filter → `is_hit = false` for every molecule (explicit; not vacuous truth). FE disables "Add only hits" toggle and forces scope = `all`. Backend behaves deterministically if a caller submits `scope=hits_only` with no active filter — returns zero rows. |

---

## 4. B1, B5, B7, B8 — Grid polish

### 4.1. B1 — Structure thumbnails

New shared component `frontend/src/shared/components/molecule-thumbnail.tsx`. Wraps the existing depiction utility (location confirmed during implementation phase — likely under `features/chemical-registration/` or `shared/lib/rdkit`). Props: `smiles: string | null | undefined`, `size: "sm" | "md" | "lg"`, `fallback?: ReactNode`. Cached via TanStack Query keyed on SMILES. Falls back to text reg-id on null/error.

Render sites:
- `results-grid.tsx` compound column — `size="sm"` (48×36).
- `decision-panel.tsx` header — `size="md"` (200×150) with hover-to-expand to `lg`.
- `<AddFromRunsDialog>` preview table — `size="sm"`.

### 4.2. B5 — Chip filter row

New component `frontend/src/features/screen-campaign/components/campaign-filter-bar.tsx`. Rendered in `campaign-builder.tsx` above the results grid, below the sticky header. Three groups:
- **Decision:** `Selected (N)` `Deferred (N)` `Rejected (N)` — click toggles inclusion.
- **Hit status:** `Hits (N)` `Non-hits (N)` `ND (N)` — derived from each row's hit_call across channels (any-hit semantics for the chip count).
- **Audit:** `Overridden only ✓` toggle.

State lives in `campaign-builder.tsx`. AG Grid receives `isExternalFilterPresent` + `doesExternalFilterPass` callbacks; combines with AG Grid's quick-filter (both coexist).

### 4.3. B7 — Qualifier-aware override gating

- Backend (`domain/research_organization/campaign_measurement.py`): relax `__post_init__` — allow empty `unit` when `value_qualifier ∈ {nd, excluded}`; force `value = None` for these qualifiers (validates rather than silently overrides).
- FE (`<OverrideModal>` in `results-grid.tsx`): watch the qualifier dropdown. When `nd`/`excluded` selected, disable + clear value/unit inputs.

### 4.4. B8 — Override reason

- Migration 028 column: `campaign_measurement.override_reason: text NULL`.
- `OverrideResultCellCommand` field: `reason: str | None = None`.
- `CampaignMeasurementResponse` field: `override_reason: str | None`.
- DAIKON `_serialize_measurement` (in `get_published_campaign.py`): include `override_reason` in the source-block.
- `<OverrideModal>` textarea below the value/unit row. **Required** when:
  - `is_manual_override` is becoming `true` (new or changed override), AND
  - the submitted `value`/`qualifier`/`unit` differs from the auto-resolved measurement.
- Display: existing `OVR` badge in grid gains a hover tooltip showing the reason.

### 4.5. "Preview as published" (1-hour bonus)

Button in builder header → opens a modal that renders the draft campaign through the existing `get_published_campaign._serialize_*` helpers, via a lightweight endpoint `GET /api/v1/campaigns/{id}/preview-published` that bypasses the closed-status guard for DRAFT campaigns (auth still required). **100 % reuse** of the DAIKON serializer — no new shape code.

---

## 5. Data model — migration 028

New columns on `campaign_measurement`, all nullable for backwards compat:

| Column | Type | Notes |
|---|---|---|
| `override_reason` | text NULL | B8; populated by override use case |
| `test_concentration_value` | float NULL | Snapshot at import; null for legacy rows |
| `test_concentration_unit` | varchar(32) NULL | Snapshot at import |
| `replicate_count` | integer NULL | Snapshot at import |
| `qc_pass` | boolean NULL | Snapshot at import |
| `contributing_run_ids` | UUID[] NULL | Snapshot — runs that fed the selection rule (NULL when single run; `source_run_id` carries it) |

Existing rows: all new columns `NULL`. `_serialize_measurement` **always emits** the new fields (as `null` when absent) to keep the DAIKON schema flat — consumers can rely on field presence. Closed campaigns made before this migration remain valid (their measurements simply emit `null` for the new fields).

---

## 6. DRY map (must reuse, must not reinvent)

| Need | Reuse | Path |
|---|---|---|
| Hit-call evaluator | `_compute_hit_call(value, criterion)` | `application/research_organization/channel_resolution.py:99` |
| Channel value resolution | existing resolver | `application/research_organization/channel_resolution.py` |
| Aggregated run data | `find_aggregated_by_molecules` | `infrastructure/persistence/sqlalchemy/screening_assay/readout_data_repository.py` |
| Run lookups | `RunRepository.find_by_ids` (add bulk method if missing) | `infrastructure/persistence/sqlalchemy/screening_assay/run_repository.py` |
| DAIKON-shape serialization | `_serialize_*` helpers | `application/research_organization/get_published_campaign.py` |
| Existing dialog primitives | `<Dialog>`, `<Checkbox>`, `<Command>` | `frontend/src/shared/components/ui/` |
| Existing single-select picker | `<SearchableSelect>` (adapt to multi or wrap with checkbox-list inside `<Command>`) | `frontend/src/shared/components/searchable-select.tsx` |
| (Deferred to B2) Curve fitting | `LmfitCurveFitter` | `infrastructure/lmfit/curve_fitter.py` |
| (Deferred to B2) Curve rendering | `<DoseResponseChart>`, `<DoseResponseSparkline>` | `frontend/src/features/screening-assay/components/` |

---

## 7. Testing

### Backend
- ~15 unit tests (preview UC, add UC, measurement validation, override w/ reason).
- ~3 integration tests (multi-run end-to-end, migration 028 dry-run on populated DB, locked-campaign immutability).
- ~4 API tests (preview shape contract, add single-run case, add multi-run case, locked-423).
- Parity test: preview and add return identical hit-calls for identical inputs (parameterized fixture, single source of truth).

### Frontend
- `pnpm tsc --noEmit` clean across all FE commits.
- Manual smoke checklist (post-implementation, see §9).
- Component tests deferred (project has no Jest/Vitest config). Playwright stub remains the follow-up.

---

## 8. Risks & open questions (resolve in implementation phase 1)

- **`is_primary` on `ReadoutDefinition`?** If the schema has it, default `Use ✓` is the primary readout only; otherwise default is all readouts with criteria.
- **Existing depiction component location.** Confirm path before B1 wiring; build a thin wrapper if no shared component exists.
- **`<SearchableSelect>` multi-select cost.** If adaptation > ~30 min, fall back to a checkbox list inside `<Command>` directly in `<AddFromRunsDialog>`.
- **Chip-filter ↔ AG Grid quick-filter coexistence.** Verify; prefer the chip-bar as primary if conflict.
- **`is_outlier` on `ReadoutData`** — does the aggregated query already exclude outliers? Confirm; otherwise apply at preview time.

---

## 9. Manual smoke checklist (post-implementation)

1. Multi-run picker — tick 2 runs from same protocol; channel cards consolidate to one per readout.
2. Edit IC50 criterion; preview re-fires within ~300 ms; hit count updates live.
3. Toggle AND/OR; counts shift accordingly.
4. Toggle "Add only hits"; commit-button label updates live.
5. Commit; grid shows new channels, thumbnails on every row, chip-filter bar above the grid.
6. Click `Selected` decision chip; grid filters; counts in chips remain accurate.
7. Click a cell, override with a different value; reason textarea is **required** to save.
8. Open override modal; set qualifier to `nd`; value/unit fields disable and clear.
9. Click "Preview as published"; modal renders DAIKON shape against the live draft.
10. Close & sign the campaign; closed view shows same thumbnails, chips, override reasons; published JSON includes the new snapshot fields.

---

## 10. Open follow-ups (deferred from this session)

- B2 (DR curve preview), B3 (bulk decision), B4 (bulk remove), B9 (CSV export), B10 (staleness signal), B11 (sources card on drafts), B12 (workspace-wide list), B13 (per-row audit history).
- A1–A5 (real e-sig, name/signed_at resolution, DAIKON transport, real 423 test, SavedSearch).
- C1–C4 (integrity proofs).
- D1–D7 (plumbing: orval-zod, Playwright config, viewer guard, RecomputeChannel route, etc.).
- E1–E5 (concept: published meaning, compare-with-supersede, templates, replicate drill-in, ELN linkage).

Full punch list: `docs/backlog/screen-campaign-followups.md`.
