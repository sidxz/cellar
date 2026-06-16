# SAR Unit C items 3+4+5 — design (state polish · docs note · helper extraction)

**Created:** 2026-06-16 · **Branch:** `design-7` · **Prev:** Unit C items 1 (`577281c5`) + 2 (`9d407413`) done.
**Scope:** the three SAR-focused remaining Unit-C items. Item 6 (E2E harness — generic app infra) is deliberately deferred to a separately-scoped project. Item 7 (board) is a tiny follow-up.

This slice is **frontend-only** (item 3, 5) + **docs-only** (item 4). No backend code, no migration, no orval regen (the cancel routes + generated fns already exist).

---

## Motivation

Unit B/C rewired the SAR workbench onto server endpoints. Three rough edges remain:

- **Item 3 — dishonest/missing states.** Activity-projection *failure is never surfaced* (only `run.error` renders); a 0-match core shows an *empty grid* with no explanation; there is *no cancel* affordance even though the backend cancel endpoints and orval functions already exist.
- **Item 5 — a component-imports-component smell + a duplicated mapper.** `rgroup-heatmap.tsx` imports `pickReference`/`potencyShade`/`snapshotFromActivity` from the sibling **component** `rgroup-table.tsx`; and `snapshotFromActivity` is byte-for-byte duplicated in `research-organization/.../dose-response-cell.tsx`.
- **Item 4 — domain-model drift.** `docs/domain-model/04-sar-analysis.md` never documents `RGroupDecompositionRun` / `SarActivityProjection` (added as async-job/read-model aggregates in Part 1b/2).

---

## Item 3 — functional-state + honest-label polish

### State taxonomy

**Decomposition lane** (driven by `core` + `run`):

| State | Trigger | UI |
|---|---|---|
| Idle | `core == null` | Core picker's own prompt; nothing else below it (no stale toggle/banner) |
| Decomposing | `run.isStarting \|\| run.isPolling` | `Decomposing… · Cancel` (Cancel → `run.cancel()`) |
| Cancelled | `run.isCancelled` | muted `Decomposition cancelled · Run again` |
| Failed | `run.error` | red `Decomposition failed: {msg} · Try again` |
| Ready, matched > 0 | `ready && matched > 0` | view toggle + count banner + table/heatmap (today's behavior) |
| No matches | `ready && matched === 0` | count banner + empty panel `No compounds matched this core. Try a different scaffold.` — **no toggle, no empty grid** |

**Activity lane** (only when `colorSpec != null`; overlays the table, never replaces it):

| State | Trigger | UI |
|---|---|---|
| Computing | `projection.isStarting \|\| projection.isPolling` | `Computing activity… · Cancel` |
| Cancelled | `projection.isCancelled` | muted `Activity computation cancelled · Run again` |
| Failed (NEW) | `projection.error` | red `Activity computation failed: {msg} · Try again` — table still renders without the activity column |
| Ready | `projectionReady` | activity column appears (today's behavior) |

`Run again` / `Try again` are explicit inline-text buttons (no autosave on a consequential action). A user-initiated **cancel is neutral** (muted copy + Run again), never styled as a failure.

### Hook changes — `use-decomposition-run`, `use-activity-projection`

Both hooks gain `cancel: () => void` and `isCancelled: boolean`, symmetrically:

- **`error` is reserved for real failures.** Today `getError` maps both `failed` *and* `cancelled` to an error string; change it to return `null` for `cancelled`. The hook return's `error` then never reflects a cancel.
- **`isCancelled`** is derived from the poll's latest `data.status === "cancelled"` **or** an optimistic local flag set by `cancel()`. The local flag resets when a new job id starts (so `Run again` clears it). `useJobPoll` already exposes the raw `data`; destructure it (currently only `result`/`error` are taken).
- **`cancel()`** calls the orval cancel fn for the current id (`cancelDecompositionRunApiV1SarDecompositionJobsRunIdCancelPost` / `cancelActivityProjection…`) and triggers a poll refetch so the terminal `cancelled` status is observed.
- **`Run again`** invalidates/refetches the *start* query. The cache lookup `find_cached` is **READY-only** (confirmed for `rgroup_decomposition_run_repository.find_cached`; the projection repo's lookup is assumed symmetric and will be confirmed in the plan), so a cancelled job is ignored and a fresh run/projection is created.

### `sar-view.tsx` rendering

Replace the three ad-hoc progress/error lines (current lines ~76–84) with the taxonomy above:
- Each progress line becomes a flex row with an inline `Cancel` button.
- Add the projection-failed line (NEW) and the cancelled lines (muted + Run again).
- Gate the view toggle + grid on `matched > 0`; render the empty panel when `ready && matched === 0`.
- Idle: rely on `RGroupCorePicker`'s existing prompt; if the picker has no empty prompt, add a single muted hint line (confirm in plan).

---

## Item 5 — extract shared SAR activity-display helpers (clean layering)

The `ActivityValue → CurveSnapshot` mapper bridges research-organization's `ActivityValue` and screening-assay's `CurveSnapshot`. `sar-analysis` already depends on `research-organization` (imports `ActivityValue` + `DoseResponseCell`), so the mapper lives with its input type to avoid a feature cycle.

- **New `research-organization/lib/activity-curve-snapshot.ts`** → `activityValueToCurveSnapshot(av: ActivityValue | null | undefined): CurveSnapshot | null` (the exact shared guard + mapping). Pure + unit test.
  - `dose-response-cell.tsx` uses it: guard → em-dash span; else `<DoseResponseFigure>`.
- **New `sar-analysis/lib/sar-activity-display.ts`** → `pickReference`, `potencyShade` (moved out of `rgroup-table.tsx`). Pure + unit test (move the existing helper tests here).
- `rgroup-table.tsx`: import `pickReference`/`potencyShade` from the sar lib; replace local `snapshotFromActivity` with `activityValueToCurveSnapshot` (re-export a `snapshotFromActivity` alias only if an external test/consumer needs the old name — otherwise inline the new import). Keep table-specific helpers (`buildRGroupColumns`, `buildActivityColumns`, `saveAllLabel`, `canSaveAll`).
- `rgroup-heatmap.tsx`: **drop the `./rgroup-table` import entirely** — `pickReference`/`potencyShade` from the sar lib, the mapper from the research-org lib. Smell killed.

Dependency direction after the change: `sar-analysis → research-organization → screening-assay` (all pre-existing). No `research-organization → sar-analysis` edge.

---

## Item 4 — domain-model deviation note (docs only)

Add a section to `docs/domain-model/04-sar-analysis.md` documenting the two async-job/read-model aggregates:
- `RGroupDecompositionRun` — job lifecycle `pending → running → ready / failed / cancelled`; identity = `membership_hash` + `core_hash` (cache key; READY-only cache hits); holds `rgroup_labels` + matched/unmatched/total counts; `RGroupAssignment` rows are the read model the `/rows` + `/heatmap` endpoints page over.
- `SarActivityProjection` — job lifecycle (same vocabulary); identity = membership + channel hash; holds `ActivityScalar` values keyed by molecule; feeds the activity column + heatmap coloring.
- Relationship to the existing `MolecularFingerprint` / `MarkushDefinition` aggregates (these are compute/read-model artifacts layered on registered molecules, not new registration state).

`docs/` is gitignored → the new content is in an already-tracked file (`04-sar-analysis.md`); confirm with `git ls-files` before committing, `git add -f` if needed.

---

## Order · tests · commits

**Order:** item 5 first (pure refactor, no behavior change, clean base) → item 3 hooks → item 3 `sar-view` → item 4 docs.

**Tests** (frontend-only; item 4 docs-only):
- `research-organization/lib/activity-curve-snapshot.test.ts` (new) — guard cases + full mapping.
- `sar-analysis/lib/sar-activity-display.test.ts` (new) — `pickReference`/`potencyShade` (moved from `rgroup-table.test.tsx`).
- `use-decomposition-run.test.tsx` / `use-activity-projection.test.tsx` — extend for `cancel()`, `isCancelled`, and `error` excluding `cancelled`.
- `sar-view.test.tsx` — orchestration smoke for the projection-failed line, the 0-matched empty panel, the cancel affordance, and cancelled → Run again.
- `dose-response-cell.test.tsx` / `rgroup-table.test.tsx` / `rgroup-heatmap.test.tsx` — keep green; update imports.

**Gates per touched path:** `pnpm exec vitest run <paths>` + `pnpm exec tsc --noEmit` (catches orval boundary cast drift) + `pnpm exec biome check <impl> <test>` — write with `--write` first, then verify **exit 0** (never trust piped output; biome format is error-severity).

**Commits** (explicit pathspec, from `frontend/` for code / repo root for docs; trailer `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`):
1. `refactor(sar)` — item 5 mapper + potency-helper extraction.
2. `feat(sar)` — item 3 hook `cancel()`/`isCancelled`.
3. `feat(sar)` — item 3 `sar-view` states/copy + cancel affordance.
4. `docs(sar)` — item 4 domain-model note.

---

## Non-goals / out of scope

- No backend changes, no migration, no orval regen (cancel routes + fns exist).
- No full component render-flow test (still deferred to the item-6 E2E harness).
- No new aggregation/coloring behavior — purely state/copy/extraction.
- Item 6 (E2E harness) and item 7 (board update) are out of this slice.

## To confirm during planning

- Projection repo cache lookup is READY-only (symmetric to the run repo) — needed for projection `Run again`.
- `RGroupCorePicker` already renders an idle "pick/draw a core" prompt (else add a one-line hint).
- Whether any external consumer/test depends on the `snapshotFromActivity` name (drives alias-vs-inline).
- Exact orval fn name for the activity-projection cancel (mirror the `getActivityProjection…ProjectionIdGet` casing gotcha).
