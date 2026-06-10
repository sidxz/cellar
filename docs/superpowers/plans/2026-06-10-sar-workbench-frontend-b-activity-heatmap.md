# SAR Workbench — Frontend Plan B (Activity coloring + Heatmap) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add activity to the SAR view built in Plan A — a "Color by" control (protocol → readout/intercept → aggregation), activity-colored cells + row→dose-response in the R-group table, and a 2-axis R-group **heatmap** (table ⇄ heatmap sub-toggle).

**Architecture:** `SarView` (from Plan A) gains a `colorSpec` + aggregation state and fetches activity for its molecule set by REUSING the search machinery (`useExecuteSearch` with a `keyword_list` criterion). The chosen activity (one readout/intercept) is passed to both the R-group table (new value + sparkline columns, Δ-vs-reference shading, row→curve) and a new heatmap component. No new backend work — the endpoint + enrichment already exist.

**Tech Stack:** Next.js 16 / React 19 / TS / TanStack Query v5 / AG Grid (table) + custom CSS grid (heatmap) / RDKit.js / orval types / vitest.

**Spec:** `docs/superpowers/specs/2026-06-09-sar-workbench-rgroup-design.md` (Phase 1). **Depends on:** Plan A (`2026-06-09-sar-workbench-frontend-a-foundation.md`) — `SarView`, `RGroupTable`/`buildRGroupRows`/`buildRGroupColumns`, `RGroupCorePicker`, `useRGroupDecomposition`, the `sar` view-mode. All committed on `design-6`.

**Scope decision (read before starting):**
- Plan B operates on the **same molecule set the SAR view already uses** (`SarView.props.molecules` — the loaded set). The activity fetch is scoped to those molecule ids, so the heatmap/table/decomposition stay mutually consistent (all on the loaded set), and the UI labels it honestly ("N loaded", from Plan A). **Full-collection coverage is a deliberate, separate follow-up** (it changes how `SarView` sources its molecules at the collection-detail seam, benefiting Plan A's table AND Plan B's heatmap uniformly). Record it in `docs/backlog/` (Task B5 verification step). Do NOT try to solve full-collection loading inside Plan B.
- **Single-readout guardrail (from the research/spec):** the color control selects exactly ONE protocol + ONE readout/intercept. Activity scalars are only ever compared within that one readout — never mixed across protocols/readouts. This is enforced structurally by the control (one selection at a time).

**Verified reuse APIs (confirmed against the live code — adapt only if a signature differs):**
- **Activity fetch:** `useExecuteSearch` (`features/research-organization/hooks/use-search.ts`) → `mutateAsync({ input, limit })`; `input: ExecuteSearchInput = { query, protocol_columns?, aggregation? }`. Scope to a fixed set with one criterion: `{ type: "keyword_list", values: moleculeIds, ref_type: "uuid" }` (types in `features/research-organization/types`). Response `EnrichedSearchResponse.activity_data?: Record<molId, Record<colId, ActivityValue>>`.
- **Protocol column tokens** (`features/research-organization/lib/protocol-column-id.ts`): `drcColId(readoutDefId)` → `drc:<rd>`; `rdColId(protocolId, readoutDefId)` → `rd:<proto>:<rd>`; `toBackendProtocolColumns(cols)` collapses FE-only `drc:<rd>:<kind>:<level>` → `drc:<rd>` before sending (MUST call before the request). The `activity_data` key for a DR readout is the canonical `drc:<rd>`.
- **Aggregation** (`features/research-organization/lib/use-aggregation-mode.ts`): `AggregationMode` = `"latest"|"gmean"|"mean"|"best_r2"`; `aggregationModeToWire(mode): SelectionRule`. Control: `AggregationControl` (`components/search/aggregation-control.tsx`, props `{mode, onChange, disabled?}`) — reuse as-is.
- **Readout/intercept options** (`features/research-organization/lib/activity-where-options.ts`): `buildActivityWhereOptions(protocol: Protocol | undefined): WhereOption[]`, where `WhereOption = { id, label, unit?, source: "dr_curve"|"readout_data"|"curve_class", readout_definition_id, intercept_key: InterceptKey | null, group }`. Use the DR + numeric options (skip `curve_class` for coloring — it's categorical, not a scalar). `parseWhereOptionId(id)` reverses it.
- **Protocols:** `useProtocolSummaries(projectIds?, { includeAll? })` (`features/screening-assay/hooks/use-protocols.ts`) → `ProtocolSummary[]` (for the protocol picker); `useProtocol(id)` → full `Protocol` (has `readout_definitions`, needed by `buildActivityWhereOptions`).
- **Scalar + label** (`features/screening-assay/lib/intercept-label.ts`): `findInterceptValue(av.intercept_values, spec)` → `InterceptValue | undefined`; `interceptLabel(spec)`. Scalar precedence (mirror `intercept-cell.tsx`): keyed intercept value → `av.value`.
- **Sparkline / curve:** `DoseResponseCell` (`components/search/dose-response-cell.tsx`, props `{ value?: ActivityValue }`) for the table cell; `DoseResponseFigure` (`features/screening-assay/components/dose-response-figure.tsx`, props `{ curve, size, unit, interactive }`) for the row/cell-click expand. Build a `CurveSnapshot` from an `ActivityValue` exactly as `dose-response-cell.tsx` does.
- **DataGrid / structure:** as Plan A (`DataGrid`, `structureColumn`, `StructureThumbnail`).
- **`ActivityValue` type** (`features/research-organization/types`): `{ value, qualifier, unit, source, curve_type, r_squared, intercept_values?, curve_params, raw_data, additional_curves?, aggregate?, ... }`.
- Tests: `cd frontend && pnpm test -- <path>` (vitest); lint `cd frontend && pnpm lint` (verify by EXIT CODE); **typecheck `cd frontend && pnpm exec tsc --noEmit` (run this in each task — vitest/biome do NOT typecheck; a type error breaks `next build`).** No Playwright.

---

## Task B1: "Color by" control

**Files:**
- Create: `frontend/src/features/sar-analysis/lib/sar-color-spec.ts` (the pure spec type + WhereOption→spec/token mapping)
- Create: `frontend/src/features/sar-analysis/components/rgroup-color-control.tsx`
- Test: `frontend/src/features/sar-analysis/lib/sar-color-spec.test.ts` + `rgroup-color-control.test.tsx`

**The spec type (pure, testable):**
```ts
import type { InterceptKey } from "@/features/research-organization/types";

/** The single activity dimension the SAR view colors by. */
export interface SarColorSpec {
  protocolId: string;
  /** The activity_data column key (canonical): drc:<rd> or rd:<proto>:<rd>. */
  column: string;
  /** For DR sources, which intercept's scalar to read (null = primary → av.value). */
  interceptKey: InterceptKey | null;
  source: "dr_curve" | "readout_data";
  /** Display label, e.g. "EGFR binding · IC50". */
  label: string;
}
```

- [ ] **Step 1: failing test** — `sar-color-spec.test.ts`: assert `whereOptionToColorSpec(protocolId, protocolName, option)` maps a DR `WhereOption` to `{ column: "drc:<rd>", interceptKey, source:"dr_curve" }` and a numeric `WhereOption` to `{ column: "rd:<proto>:<rd>", source:"readout_data" }`; and `colorSpecScalar(av, spec)` returns the keyed-intercept value (or `av.value` when `interceptKey` is null). Write the cases first:
```ts
import { describe, expect, it } from "vitest";
import { colorSpecScalar, whereOptionToColorSpec } from "./sar-color-spec";

const drOpt = { id: "dr_curve:rd1", label: "IC50", source: "dr_curve", readout_definition_id: "rd1", intercept_key: null, group: "dose_response" } as const;
const numOpt = { id: "readout_data:rd2", label: "%Inh", source: "readout_data", readout_definition_id: "rd2", intercept_key: null, group: "numeric_readout" } as const;

describe("sar-color-spec", () => {
  it("maps a DR where-option to a drc column", () => {
    const s = whereOptionToColorSpec("p1", "EGFR", drOpt as never);
    expect(s.column).toBe("drc:rd1");
    expect(s.source).toBe("dr_curve");
    expect(s.label).toMatch(/EGFR/);
  });
  it("maps a numeric where-option to an rd column", () => {
    const s = whereOptionToColorSpec("p1", "EGFR", numOpt as never);
    expect(s.column).toBe("rd:p1:rd2");
  });
  it("reads the primary scalar from av.value when interceptKey is null", () => {
    const av = { value: 42, intercept_values: null } as never;
    expect(colorSpecScalar(av, { interceptKey: null } as never)).toBe(42);
  });
  it("reads a keyed intercept scalar via findInterceptValue", () => {
    const av = { value: 1, intercept_values: [{ spec: { kind: "ic", level: 90 }, value: 7 }] } as never;
    expect(colorSpecScalar(av, { interceptKey: { kind: "ic", level: 90 } } as never)).toBe(7);
  });
});
```

- [ ] **Step 2: run → FAIL.** `cd frontend && pnpm test -- src/features/sar-analysis/lib/sar-color-spec.test.ts`

- [ ] **Step 3: implement `sar-color-spec.ts`** (reuse the real formatters; adapt `findInterceptValue`'s spec arg shape to the real `InterceptSpec`):
```ts
import { drcColId, rdColId } from "@/features/research-organization/lib/protocol-column-id";
import type { WhereOption } from "@/features/research-organization/lib/activity-where-options";
import type { ActivityValue } from "@/features/research-organization/types";
import { findInterceptValue } from "@/features/screening-assay/lib/intercept-label";
// NOTE: define the `SarColorSpec` interface (shown above) at the top of THIS
// same file; do not create a separate .types file. Other tasks import it via
// `import type { SarColorSpec } from "../lib/sar-color-spec"`.

export function whereOptionToColorSpec(
  protocolId: string,
  protocolName: string,
  opt: WhereOption,
): SarColorSpec {
  const column =
    opt.source === "readout_data"
      ? rdColId(protocolId, opt.readout_definition_id)
      : drcColId(opt.readout_definition_id);
  return {
    protocolId,
    column,
    interceptKey: opt.intercept_key,
    source: opt.source === "readout_data" ? "readout_data" : "dr_curve",
    label: `${protocolName} · ${opt.label}`,
  };
}

/** The number used to color a cell, mirroring intercept-cell.tsx precedence. */
export function colorSpecScalar(av: ActivityValue | undefined, spec: SarColorSpec): number | null {
  if (!av) return null;
  if (spec.interceptKey) {
    const iv = findInterceptValue(av.intercept_values, {
      kind: spec.interceptKey.kind,
      level: spec.interceptKey.level,
    } as never); // adapt to the real InterceptSpec shape
    return iv?.value ?? null;
  }
  return av.value ?? null;
}
```
(Keep `SarColorSpec` in this file or a `.types.ts`; the test imports the functions. ADAPT the `findInterceptValue` spec argument to the real `InterceptSpec` type — read `intercept-label.ts`.)

- [ ] **Step 4: implement `rgroup-color-control.tsx`** — a compact "Color by: [protocol ▾] [readout ▾] · [AggregationControl]". Spec:
  - Props: `{ projectIds?: string[]; value: SarColorSpec | null; onChange: (spec: SarColorSpec | null) => void; aggregationMode: AggregationMode; onAggregationChange: (m: AggregationMode) => void }`.
  - Protocol `Select` from `useProtocolSummaries(projectIds, { includeAll: true })`.
  - On protocol pick, `useProtocol(protocolId)` → `buildActivityWhereOptions(protocol)`, filter to `group !== "curve_class"` (scalar readouts only), render a readout/intercept `Select` of those `WhereOption`s (label them with `interceptLabel`/`opt.label`).
  - On readout pick → `onChange(whereOptionToColorSpec(protocolId, protocolName, opt))`.
  - Render `<AggregationControl mode={aggregationMode} onChange={onAggregationChange} />` (only meaningful for DR; fine to always show).
  - Reuse `Select` from `@/shared/components/ui/select` and the `useProtocol` hook. Test with mocked hooks (assert picking protocol+readout emits the right `SarColorSpec`).

- [ ] **Step 5: run tests + typecheck + lint.** `cd frontend && pnpm test -- src/features/sar-analysis/lib/sar-color-spec.test.ts src/features/sar-analysis/components/rgroup-color-control.test.tsx && pnpm exec tsc --noEmit && pnpm lint` (lint exit 0).

- [ ] **Step 6: commit.**
```bash
git commit -m "feat(sar): activity color-by control (protocol/readout/aggregation)" -- frontend/src/features/sar-analysis/lib/sar-color-spec.ts frontend/src/features/sar-analysis/lib/sar-color-spec.test.ts frontend/src/features/sar-analysis/components/rgroup-color-control.tsx frontend/src/features/sar-analysis/components/rgroup-color-control.test.tsx
```

---

## Task B2: SAR activity fetch hook

**Files:**
- Create: `frontend/src/features/sar-analysis/hooks/use-sar-activity.ts`
- Test: `frontend/src/features/sar-analysis/hooks/use-sar-activity.test.tsx`

**Responsibility:** given `moleculeIds`, a `SarColorSpec | null`, and an `AggregationMode`, fetch activity via `useExecuteSearch` and return `{ activityByMolecule: Record<molId, ActivityValue | undefined>, isFetching }`. Reuses `toBackendProtocolColumns` + `aggregationModeToWire`. Returns empty when no colorSpec.

- [ ] **Step 1: failing test** (`.test.tsx`): inject an `executeFn` that resolves `{ activity_data: { m1: { "drc:rd1": { value: 12 } } } }`; render the hook with `moleculeIds:["m1"]`, a DR colorSpec (`column:"drc:rd1"`), mode `"latest"`; assert `executeFn` was called with an input whose query has a `keyword_list` criterion `{ values:["m1"], ref_type:"uuid" }`, `protocol_columns: ["drc:rd1"]`, `aggregation: "latest_approved_run"`; and `activityByMolecule.m1.value === 12`.

- [ ] **Step 2: run → FAIL.**

- [ ] **Step 3: implement:**
```ts
"use client";

import { useExecuteSearch } from "@/features/research-organization/hooks/use-search";
import { toBackendProtocolColumns } from "@/features/research-organization/lib/protocol-column-id";
import { aggregationModeToWire, type AggregationMode } from "@/features/research-organization/lib/use-aggregation-mode";
import type { ActivityValue } from "@/features/research-organization/types";
import { useEffect, useState } from "react";
import type { SarColorSpec } from "../lib/sar-color-spec";

export function useSarActivity(args: {
  moleculeIds: string[];
  colorSpec: SarColorSpec | null;
  aggregationMode: AggregationMode;
}) {
  const search = useExecuteSearch();
  const [activityByMolecule, setActivity] = useState<Record<string, ActivityValue | undefined>>({});

  // Re-fetch when the set / color column / aggregation changes.
  // biome-ignore lint/correctness/useExhaustiveDependencies: search.mutateAsync identity is stable enough; refetch keyed on the value deps below
  useEffect(() => {
    if (!args.colorSpec || args.moleculeIds.length === 0) {
      setActivity({});
      return;
    }
    const column = args.colorSpec.column;
    let cancelled = false;
    search
      .mutateAsync({
        input: {
          query: {
            criteria: [{ type: "keyword_list", values: args.moleculeIds, ref_type: "uuid" }],
            logic: "and",
          },
          protocol_columns: toBackendProtocolColumns([column]),
          aggregation: aggregationModeToWire(args.aggregationMode),
        },
        limit: args.moleculeIds.length,
      })
      .then((res) => {
        if (cancelled) return;
        const out: Record<string, ActivityValue | undefined> = {};
        for (const [molId, cols] of Object.entries(res.activity_data ?? {})) {
          out[molId] = cols[column];
        }
        setActivity(out);
      })
      .catch(() => { if (!cancelled) setActivity({}); });
    return () => { cancelled = true; };
  }, [args.moleculeIds.join(","), args.colorSpec?.column, args.aggregationMode]);

  return { activityByMolecule, isFetching: search.isPending };
}
```
ADAPT: confirm `useExecuteSearch().mutateAsync` accepts `{ input, limit }` (it does per `use-search.ts`); make `executeFn` injectable for the test (add an optional `opts?: { executeFn?: ... }` param defaulting to the hook, OR mock `useExecuteSearch` in the test). Confirm `SearchCriterion`/`ExecuteSearchInput` accept the `keyword_list` shape (they do). NOTE the `moleculeIds.join(",")` dep avoids the unstable-array-identity refetch storm (per `feedback_poll_hook_stable_job_ref`).

- [ ] **Step 4: run → PASS** + `pnpm exec tsc --noEmit` + `pnpm lint` (exit 0).
- [ ] **Step 5: commit** `git commit -m "feat(sar): activity fetch hook for the SAR view" -- frontend/src/features/sar-analysis/hooks/use-sar-activity.ts frontend/src/features/sar-analysis/hooks/use-sar-activity.test.tsx`

---

## Task B3: Activity columns + Δ-shading + row→curve in the R-group table

**Files:**
- Modify: `frontend/src/features/sar-analysis/components/rgroup-table.tsx` (+ its test)

**Responsibility:** when a `colorSpec` + `activityByMolecule` are provided, append two columns to the R-group table: an **activity value** column (formatted scalar, shaded green→red relative to the most-potent reference) and a **dose-response** sparkline column (`DoseResponseCell`); and a **row click → dose-response** expansion (a dialog with `DoseResponseFigure size="expand"`). Keep the structure/R-group/physchem columns from Plan A. When no colorSpec, the table is unchanged.

- [ ] **Step 1: failing test** — extend `rgroup-table.test.tsx`: a new exported pure helper `buildActivityColumns(colorSpec, activityByMolecule, referenceScalar)` returns a value column (colId `activity:value`) + a plot column (colId `activity:plot`); assert the value column's `valueGetter` reads `colorSpecScalar(activityByMolecule[row.id], colorSpec)`, and a `potencyShade(scalar, reference)` pure helper returns a green class for potent (scalar ≤ reference) and red-ish for weak. Write concrete cases.

- [ ] **Step 2: run → FAIL.**

- [ ] **Step 3: implement.** Add to `rgroup-table.tsx`:
  - `potencyShade(scalar, reference): string` — pure: returns a tailwind bg class on a green→red ramp keyed on `log10(scalar/reference)` (lower scalar = more potent = greener). For null → "".
  - `pickReference(rows, colorSpec, activityByMolecule): number | null` — the most-potent (min) non-null scalar (for IC50/EC50 lower is better; document the assumption; a future control can flip it).
  - `buildActivityColumns(colorSpec, activityByMolecule, reference)`: a value `ColDef` (valueGetter = `colorSpecScalar`, valueFormatter to 3 sig figs + unit, `cellClass`/`cellStyle` = `potencyShade(scalar, reference)`) and a `DoseResponseCell` plot `ColDef` (cellRenderer reads `activityByMolecule[row.id]`).
  - `RGroupTable` now takes optional `colorSpec?: SarColorSpec | null` + `activityByMolecule?: Record<string, ActivityValue | undefined>`; when present, appends `buildActivityColumns(...)` (between R-groups and physchem) and wires `onRowClick` to open a dialog rendering `<DoseResponseFigure curve={snapshotFrom(activityByMolecule[id])} size="expand" interactive />`.
  - Reuse the `CurveSnapshot` builder from `dose-response-cell.tsx` (extract it to a shared helper if not exported, or inline the same mapping).
  ADAPT: the `DoseResponseCell` import + the `CurveSnapshot` mapping (copy from `dose-response-cell.tsx`); the dialog can reuse `@/shared/components/ui/dialog`.

- [ ] **Step 4: run → PASS** + `pnpm exec tsc --noEmit` + `pnpm lint`.
- [ ] **Step 5: commit** `git commit -m "feat(sar): activity columns + potency shading + row→curve in R-group table" -- frontend/src/features/sar-analysis/components/rgroup-table.tsx frontend/src/features/sar-analysis/components/rgroup-table.test.tsx`

---

## Task B4: The 2-axis R-group heatmap

**Files:**
- Create: `frontend/src/features/sar-analysis/lib/rgroup-heatmap-grid.ts` (pure grid builder)
- Create: `frontend/src/features/sar-analysis/components/rgroup-heatmap.tsx`
- Test: `frontend/src/features/sar-analysis/lib/rgroup-heatmap-grid.test.ts` + `rgroup-heatmap.test.tsx`

**Responsibility:** given the decomposition (R-groups per molId), the chosen `activityByMolecule` scalars, and two axis labels (`axisY`, `axisX` ∈ `rgroup_labels`), build a 2D grid: distinct `axisY` substituent values × distinct `axisX` substituent values; each cell holds the molecules with that (Ry, Rx) combination and the best (most-potent) scalar + count. Render as a colored CSS grid; empty cells = synthesis gaps; cells with >1 compound show a "+N" badge; clicking a populated cell opens the compound(s)/curve.

**Pure builder (the testable core):**
```ts
export interface HeatmapCell {
  yValue: string; xValue: string;
  moleculeIds: string[];
  bestScalar: number | null;   // most potent among the cell's molecules
}
export interface HeatmapGrid {
  yValues: string[]; xValues: string[];
  cells: Record<string, HeatmapCell>;  // key `${yValue}__${xValue}`
}
export function buildHeatmapGrid(
  assignments: { molecule_id: string; rgroups: Record<string, string> }[],
  axisY: string, axisX: string,
  scalarOf: (molId: string) => number | null,
): HeatmapGrid { /* group by (rgroups[axisY], rgroups[axisX]); best = min non-null scalar */ }
```

- [ ] **Step 1: failing test** (`rgroup-heatmap-grid.test.ts`): 3 assignments over R1×R2; assert `yValues`/`xValues` are the distinct sorted substituents, a 2-compound cell collapses to `moleculeIds.length===2` with `bestScalar` = the more-potent value, and a missing combo has no cell (gap).

- [ ] **Step 2: run → FAIL.**

- [ ] **Step 3: implement the builder** (pure; group assignments by the two axis substituent SMILES; `bestScalar` = min of non-null scalars; sort axis values).

- [ ] **Step 4: implement `rgroup-heatmap.tsx`** — spec:
  - Props: `{ decomposition: RGroupDecompositionResponse; activityByMolecule: Record<string, ActivityValue|undefined>; colorSpec: SarColorSpec | null; molecules: Molecule[]; }`.
  - Axis pickers: two `Select`s over `decomposition.rgroup_labels` (default axisY = labels[0], axisX = labels[1] ?? labels[0]).
  - `scalarOf = (molId) => colorSpecScalar(activityByMolecule[molId], colorSpec)`. Build grid via `buildHeatmapGrid`.
  - Render a CSS grid (`<table>` or `display:grid`): column headers = `xValues` (render each substituent via `StructureThumbnail size={32}` + SMILES), row headers = `yValues`; each cell = `potencyShade(bestScalar, reference)` background + the formatted scalar + a `+N` badge when `moleculeIds.length>1`; empty cells (no grid entry) = hatched "make?" gap. Reuse `potencyShade`/`pickReference` from Task B3 (export them).
  - Click a populated cell → a dialog listing the cell's compounds (reg# + `StructureThumbnail`) and, for each, a `DoseResponseCell`/`DoseResponseFigure`.
  - Legend (potent→weak) + the active readout label (`colorSpec.label`). Empty state when `colorSpec` is null ("Pick an activity to color the heatmap").
  - Test (`rgroup-heatmap.test.tsx`): mock heavy children; assert the grid renders the right number of rows/cols for a fixture decomposition + the gap/`+N` rendering.

- [ ] **Step 5: run tests + typecheck + lint.** `cd frontend && pnpm test -- src/features/sar-analysis/lib/rgroup-heatmap-grid.test.ts src/features/sar-analysis/components/rgroup-heatmap.test.tsx && pnpm exec tsc --noEmit && pnpm lint`.

- [ ] **Step 6: commit** `git commit -m "feat(sar): 2-axis R-group heatmap" -- frontend/src/features/sar-analysis/lib/rgroup-heatmap-grid.ts frontend/src/features/sar-analysis/lib/rgroup-heatmap-grid.test.ts frontend/src/features/sar-analysis/components/rgroup-heatmap.tsx frontend/src/features/sar-analysis/components/rgroup-heatmap.test.tsx`

---

## Task B5: Wire color-by + activity + table/heatmap sub-toggle into SarView

**Files:**
- Modify: `frontend/src/features/sar-analysis/components/sar-view.tsx` (+ its test)

**Responsibility:** `SarView` gains `colorSpec` + `aggregationMode` state, renders `RGroupColorControl`, fetches activity via `useSarActivity`, and renders a **Table ⇄ Heatmap** sub-toggle that switches between `RGroupTable` (now passed `colorSpec` + `activityByMolecule`) and `RGroupHeatmap`. Disable the Heatmap sub-toggle when `decomposition.rgroup_labels.length < 2` (needs 2 axes) and when no `colorSpec`.

- [ ] **Step 1: failing test** — extend `sar-view.test.tsx`: mock `useSarActivity` + the children; assert the color control renders, picking a colorSpec triggers the activity fetch, and the Table/Heatmap sub-toggle switches the rendered child. Keep existing tests green.

- [ ] **Step 2: run → FAIL.**

- [ ] **Step 3: implement** — in `sar-view.tsx`:
  - Add state: `const [colorSpec, setColorSpec] = useState<SarColorSpec | null>(null); const [aggMode, setAggMode] = useState<AggregationMode>("latest"); const [sub, setSub] = useState<"table" | "heatmap">("table");`
  - `const { activityByMolecule } = useSarActivity({ moleculeIds, colorSpec, aggregationMode: aggMode });`
  - Render `<RGroupColorControl projectIds={...} value={colorSpec} onChange={setColorSpec} aggregationMode={aggMode} onAggregationChange={setAggMode} />` above the result.
  - A sub-toggle (two buttons Table/Heatmap, mirroring `view-mode-toggle` styling); Heatmap disabled when `!result || result.rgroup_labels.length < 2 || !colorSpec`.
  - When `sub === "heatmap"`: render `<RGroupHeatmap decomposition={result} activityByMolecule={activityByMolecule} colorSpec={colorSpec} molecules={props.molecules} />`; else `<RGroupTable decomposition={result} molecules={props.molecules} onSaveSelection={setSaveIds} colorSpec={colorSpec} activityByMolecule={activityByMolecule} />`.
  - `projectIds` for the color control: derive from the collection's project if available, else `undefined` (pass `[]`/undefined → `includeAll`). Keep simple.

- [ ] **Step 4: run tests + typecheck + lint.** `cd frontend && pnpm test -- src/features/sar-analysis/ && pnpm exec tsc --noEmit && pnpm lint`.

- [ ] **Step 5: commit** `git commit -m "feat(sar): wire color-by + activity + table/heatmap sub-toggle into SarView" -- frontend/src/features/sar-analysis/components/sar-view.tsx frontend/src/features/sar-analysis/components/sar-view.test.tsx`

---

## Plan B Done — verification

- [ ] `cd frontend && pnpm test` (full suite) — green.
- [ ] `cd frontend && pnpm exec tsc --noEmit` — 0 errors (the gate vitest/biome miss).
- [ ] `cd frontend && pnpm lint` — exit 0.
- [ ] Manual smoke (backend on :8000, `pnpm dev`): collection → SAR → pick core → **Color by** a protocol's IC50 → table cells shade by potency, row-click shows the curve → flip to **Heatmap**, pick two R-axes → cells colored, gaps hatched, `+N` where compounds collapse, click a cell → curve(s). Confirm changing the aggregation re-fetches.
- [ ] Update the GitHub project board (SAR workbench — activity + heatmap done).
- [ ] **Backlog (write to `docs/backlog/`):** "SAR view operates on the loaded molecule set, not the full collection." Root cause: `SarView` receives the host's paginated `molecules`; decomposition + activity + heatmap all scope to that set (consistent, honestly labeled "N loaded"). Fix: load the full collection membership for the SAR view at the collection-detail seam (one change benefits Plan A's table + Plan B's heatmap uniformly) — e.g. fetch all members (the scaffold-tree route already expands `collectionId` server-side; mirror that for the SAR view) and pass the full set as `molecules`, OR decompose/activity by `collectionId` and lazily resolve molecule structure/physchem.
- [ ] **Phase 2 pointer:** activity cliffs + matched-molecular-pairs (the spec's Phase 2) build on this activity layer — out of scope for Plan B.
