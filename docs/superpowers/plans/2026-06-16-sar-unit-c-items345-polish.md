# SAR Unit C items 3+4+5 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the three SAR-focused Unit-C polish items — honest cancel/empty/projection-failed states (item 3), the domain-model aggregate note (item 4), and the activity-display helper extraction that kills the component→component import smell (item 5).

**Architecture:** Frontend-only (items 3/5) + docs-only (item 4). No backend, no migration, no orval regen — the cancel routes (`/decomposition/jobs/{id}/cancel`, `/activity-projection/jobs/{id}/cancel`) and their generated fns already exist. Two new pure libs (`research-organization/lib/activity-curve-snapshot.ts` for the `ActivityValue→CurveSnapshot` mapper, `sar-analysis/lib/sar-activity-display.ts` for the potency ramp) restore a clean dependency direction (`sar-analysis → research-organization → screening-assay`). The two SAR job hooks gain a symmetric `cancel()`/`isCancelled`/`runAgain()` trio; `runAgain()` bumps a query-key nonce so the start query re-POSTs (cache lookup is READY-only, so a cancelled job is ignored and a fresh one is created).

**Tech Stack:** Next.js / React 19 / TypeScript / TanStack Query v5 / vitest + Testing Library / Biome. Spec: `docs/superpowers/specs/2026-06-16-sar-unit-c-items345-polish-design.md`.

---

## File structure

**Create:**
- `frontend/src/features/research-organization/lib/activity-curve-snapshot.ts` — `activityValueToCurveSnapshot(av): CurveSnapshot | null` (the shared DR mapper).
- `frontend/src/features/research-organization/lib/activity-curve-snapshot.test.ts`
- `frontend/src/features/sar-analysis/lib/sar-activity-display.ts` — `pickReference`, `potencyShade` (potency ramp).
- `frontend/src/features/sar-analysis/lib/sar-activity-display.test.ts`

**Modify:**
- `frontend/src/features/research-organization/components/search/dose-response-cell.tsx` — use the mapper.
- `frontend/src/features/sar-analysis/components/rgroup-table.tsx` — drop local `pickReference`/`potencyShade`/`snapshotFromActivity`; import from the libs.
- `frontend/src/features/sar-analysis/components/rgroup-table.test.tsx` — drop the moved helper-test imports.
- `frontend/src/features/sar-analysis/components/rgroup-heatmap.tsx` — drop the `./rgroup-table` import.
- `frontend/src/features/sar-analysis/hooks/use-decomposition-run.ts` (+ `.test.tsx`) — cancel trio.
- `frontend/src/features/sar-analysis/hooks/use-activity-projection.ts` (+ `.test.tsx`) — cancel trio.
- `frontend/src/features/sar-analysis/components/sar-view.tsx` (+ `.test.tsx`) — state taxonomy.
- `docs/domain-model/04-sar-analysis.md` — aggregate note.

**Gates (run from `frontend/`):** `pnpm exec vitest run <paths>` · `pnpm exec tsc --noEmit` · `pnpm exec biome check --write <paths>` then `pnpm exec biome check <paths>` (verify **exit 0** — biome format is error severity; never trust piped output). Commit trailer: `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`. Explicit pathspec on every commit.

---

## Task 1: Extract the `ActivityValue → CurveSnapshot` mapper (item 5a)

**Files:**
- Create: `frontend/src/features/research-organization/lib/activity-curve-snapshot.ts`
- Test: `frontend/src/features/research-organization/lib/activity-curve-snapshot.test.ts`
- Modify: `frontend/src/features/research-organization/components/search/dose-response-cell.tsx`

- [ ] **Step 1: Write the failing test**

Create `frontend/src/features/research-organization/lib/activity-curve-snapshot.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { activityValueToCurveSnapshot } from "./activity-curve-snapshot";

const DR = {
  source: "dose_response",
  value: 1.5,
  r_squared: 0.98,
  unit: "uM",
  raw_data: [{ x: 1, y: 2 }],
  curve_params: { top: 100, bottom: 0, hill_slope: 1, curve_class: "full" },
  additional_curves: null,
  aggregate: null,
} as unknown as Parameters<typeof activityValueToCurveSnapshot>[0];

describe("activityValueToCurveSnapshot", () => {
  it("maps a dose-response value to a CurveSnapshot", () => {
    const snap = activityValueToCurveSnapshot(DR);
    expect(snap).toMatchObject({
      fitted_value: 1.5,
      top: 100,
      bottom: 0,
      hill_slope: 1,
      r_squared: 0.98,
      curve_class: "full",
    });
    expect(snap?.raw_data).toHaveLength(1);
  });

  it("returns null for null / undefined / non-DR / empty-raw / missing-params / missing-value", () => {
    expect(activityValueToCurveSnapshot(null)).toBeNull();
    expect(activityValueToCurveSnapshot(undefined)).toBeNull();
    expect(activityValueToCurveSnapshot({ ...DR, source: "readout_data" } as never)).toBeNull();
    expect(activityValueToCurveSnapshot({ ...DR, raw_data: [] } as never)).toBeNull();
    expect(activityValueToCurveSnapshot({ ...DR, curve_params: null } as never)).toBeNull();
    expect(activityValueToCurveSnapshot({ ...DR, value: null } as never)).toBeNull();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && pnpm exec vitest run src/features/research-organization/lib/activity-curve-snapshot.test.ts`
Expected: FAIL — cannot resolve `./activity-curve-snapshot`.

- [ ] **Step 3: Write minimal implementation**

Create `frontend/src/features/research-organization/lib/activity-curve-snapshot.ts` (mapping copied verbatim from the current `snapshotFromActivity` so behavior is identical):

```ts
import type { CurveSnapshot } from "@/features/screening-assay/components/dose-response-figure";
import type { ActivityValue } from "../types";

/**
 * Map a dose-response `ActivityValue` snapshot → the shared `CurveSnapshot`,
 * or null when the value isn't a usable DR fit (no raw points, wrong source,
 * no curve params, or no fitted value). Single source of truth for both the
 * search/SAR table cell and the SAR heatmap.
 */
export function activityValueToCurveSnapshot(
  av: ActivityValue | undefined | null,
): CurveSnapshot | null {
  if (
    !av ||
    !av.raw_data ||
    av.raw_data.length === 0 ||
    av.source !== "dose_response" ||
    av.curve_params == null ||
    av.value == null
  ) {
    return null;
  }
  return {
    fitted_value: av.value,
    top: av.curve_params.top,
    bottom: av.curve_params.bottom,
    hill_slope: av.curve_params.hill_slope,
    r_squared: av.r_squared,
    curve_class: av.curve_params.curve_class ?? null,
    raw_data: av.raw_data,
    additional_curves: av.additional_curves ?? null,
    aggregate: av.aggregate ?? null,
  };
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && pnpm exec vitest run src/features/research-organization/lib/activity-curve-snapshot.test.ts`
Expected: PASS (2 tests).

- [ ] **Step 5: Rewire `dose-response-cell.tsx` to the mapper**

In `frontend/src/features/research-organization/components/search/dose-response-cell.tsx`, replace the inline guard + mapping. New body:

```tsx
"use client";

import { DoseResponseFigure } from "@/features/screening-assay/components/dose-response-figure";
import { memo } from "react";
import { activityValueToCurveSnapshot } from "../../lib/activity-curve-snapshot";
import type { ActivityValue } from "../../types";

interface DoseResponseCellProps {
  value?: ActivityValue;
}

/**
 * Search results IC50 plot cell. Hands the (params + raw_data) tuple to
 * the shared <DoseResponseFigure /> so the search drawing matches the
 * protocol Activity tab + the campaign grid 1:1 — same component, same
 * trace builder, same color tokens, same axis-range strategy.
 */
function DoseResponseCellInner({ value }: DoseResponseCellProps) {
  const curve = activityValueToCurveSnapshot(value);
  if (!curve) {
    return <span className="text-muted-foreground">&mdash;</span>;
  }
  return <DoseResponseFigure curve={curve} size="cell" unit={value?.unit ?? null} />;
}

export const DoseResponseCell = memo(DoseResponseCellInner);
```

Note: the `CurveSnapshot` type import is dropped (the mapper owns the type now); `DoseResponseFigure` stays.

- [ ] **Step 6: Verify dose-response-cell tests + types still pass**

Run: `cd frontend && pnpm exec vitest run src/features/research-organization/components/search/dose-response-cell.test.tsx src/features/research-organization/lib/activity-curve-snapshot.test.ts`
Expected: PASS (behavior unchanged).

- [ ] **Step 7: tsc + biome**

Run:
```bash
cd frontend && pnpm exec tsc --noEmit
pnpm exec biome check --write src/features/research-organization/lib/activity-curve-snapshot.ts src/features/research-organization/lib/activity-curve-snapshot.test.ts src/features/research-organization/components/search/dose-response-cell.tsx
pnpm exec biome check src/features/research-organization/lib/activity-curve-snapshot.ts src/features/research-organization/lib/activity-curve-snapshot.test.ts src/features/research-organization/components/search/dose-response-cell.tsx
```
Expected: `tsc` clean; final `biome check` exit 0.

- [ ] **Step 8: Commit**

```bash
cd /Users/sidx/workspace/chem-vault2
git commit -m "refactor(sar): extract activityValueToCurveSnapshot mapper

Single ActivityValue->CurveSnapshot mapper in research-organization/lib
(where ActivityValue lives), consumed by the search DR cell now and the
SAR table/heatmap next — kills the byte-for-byte duplicate in
dose-response-cell. No behavior change.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>" -- \
  frontend/src/features/research-organization/lib/activity-curve-snapshot.ts \
  frontend/src/features/research-organization/lib/activity-curve-snapshot.test.ts \
  frontend/src/features/research-organization/components/search/dose-response-cell.tsx
```

---

## Task 2: Extract `pickReference`/`potencyShade`, kill the table→heatmap import (item 5b)

**Files:**
- Create: `frontend/src/features/sar-analysis/lib/sar-activity-display.ts`
- Test: `frontend/src/features/sar-analysis/lib/sar-activity-display.test.ts`
- Modify: `frontend/src/features/sar-analysis/components/rgroup-table.tsx`, `rgroup-table.test.tsx`, `rgroup-heatmap.tsx`

- [ ] **Step 1: Write the failing test** (moved verbatim from `rgroup-table.test.tsx`)

Create `frontend/src/features/sar-analysis/lib/sar-activity-display.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { pickReference, potencyShade } from "./sar-activity-display";

describe("sar-activity-display potency helpers", () => {
  it("pickReference = min non-null (most potent)", () => {
    expect(pickReference([5, null, 0.2, 1])).toBe(0.2);
    expect(pickReference([null, null])).toBeNull();
  });

  it("potencyShade greens the reference, reds far-off", () => {
    expect(potencyShade(0.2, 0.2)).toContain("green");
    expect(potencyShade(50, 0.2)).toContain("red");
    expect(potencyShade(null, 0.2)).toBe("");
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && pnpm exec vitest run src/features/sar-analysis/lib/sar-activity-display.test.ts`
Expected: FAIL — cannot resolve `./sar-activity-display`.

- [ ] **Step 3: Write the implementation** (copied verbatim from `rgroup-table.tsx`)

Create `frontend/src/features/sar-analysis/lib/sar-activity-display.ts`:

```ts
/**
 * SAR activity-display helpers — the potency ramp shared by the R-group table
 * and the heatmap. Pure; gated to `dr_curve` (lower-is-better) at the call site.
 */

/** Most-potent (min) reference scalar — LOWER-is-better (dr_curve only). */
export function pickReference(scalars: (number | null)[]): number | null {
  let ref: number | null = null;
  for (const s of scalars) {
    if (s == null || !Number.isFinite(s)) continue;
    if (ref == null || s < ref) ref = s;
  }
  return ref;
}

/** Green→red potency ramp by fold-off from the most-potent reference (dr_curve only). */
export function potencyShade(scalar: number | null, reference: number | null): string {
  if (scalar == null || reference == null) return "";
  if (!Number.isFinite(scalar) || !Number.isFinite(reference) || reference <= 0) return "";
  const fold = scalar / reference;
  if (fold <= 1) return "bg-green-600/30 text-green-900 dark:text-green-100";
  if (fold <= 3) return "bg-green-500/20 text-green-900 dark:text-green-100";
  if (fold <= 10) return "bg-amber-500/20 text-amber-900 dark:text-amber-100";
  if (fold <= 100) return "bg-orange-500/25 text-orange-900 dark:text-orange-100";
  return "bg-red-600/30 text-red-900 dark:text-red-100";
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && pnpm exec vitest run src/features/sar-analysis/lib/sar-activity-display.test.ts`
Expected: PASS (2 tests).

- [ ] **Step 5: Rewire `rgroup-table.tsx`**

In `frontend/src/features/sar-analysis/components/rgroup-table.tsx`:

1. Delete the three local functions: `pickReference` (lines ~112–120), `potencyShade` (lines ~122–132), and `snapshotFromActivity` (lines ~145–168).
2. Remove the two now-orphaned type imports — both were used **only** by the deleted `snapshotFromActivity` (verified): `import type { ActivityValue } from "@/features/research-organization/types";` (line 4) and `import type { CurveSnapshot } from "@/features/screening-assay/components/dose-response-figure";` (line 9).
3. Add imports near the other feature imports:

```ts
import { activityValueToCurveSnapshot } from "@/features/research-organization/lib/activity-curve-snapshot";
import { potencyShade } from "../lib/sar-activity-display";
```

4. At the call site in `handleRowClick` (was line ~234), change:

```ts
const snapshot = activityValueToCurveSnapshot(row.activitySnapshot);
```

`buildActivityColumns` already calls `potencyShade(...)` — now resolved from the import. Keep `buildRGroupColumns`, `buildActivityColumns`, `saveAllLabel`, `canSaveAll` exactly as they are.

- [ ] **Step 6: Update `rgroup-table.test.tsx` imports**

In `frontend/src/features/sar-analysis/components/rgroup-table.test.tsx`, change the import to drop the moved helpers (they're now tested in the lib) and delete the `describe("rgroup-table pure helpers (kept)", …)` block's two moved cases (`pickReference` + `potencyShade`); keep the `buildActivityColumns` case:

```ts
import { describe, expect, it } from "vitest";
import { buildActivityColumns, canSaveAll, saveAllLabel } from "./rgroup-table";
```

Then in that file, remove the two `it("pickReference …")` and `it("potencyShade …")` tests (lines ~19–28), leaving the `buildActivityColumns` test and the `save-all toolbar action helpers` describe intact.

- [ ] **Step 7: Rewire `rgroup-heatmap.tsx`** (kills the smell)

In `frontend/src/features/sar-analysis/components/rgroup-heatmap.tsx`, replace the offending import (line 33):

```ts
import { activityValueToCurveSnapshot } from "@/features/research-organization/lib/activity-curve-snapshot";
import { pickReference, potencyShade } from "../lib/sar-activity-display";
```

(Delete `import { pickReference, potencyShade, snapshotFromActivity } from "./rgroup-table";`.) Then at the cell-click site (line ~105) change:

```ts
const snapshot: CurveSnapshot | null = activityValueToCurveSnapshot(cell.best_snapshot as never);
```

`heatmapReference` keeps calling `pickReference` (now imported). No other change.

- [ ] **Step 8: Run all touched tests**

Run:
```bash
cd frontend && pnpm exec vitest run \
  src/features/sar-analysis/lib/sar-activity-display.test.ts \
  src/features/sar-analysis/components/rgroup-table.test.tsx \
  src/features/sar-analysis/components/rgroup-heatmap.test.tsx
```
Expected: PASS.

- [ ] **Step 9: tsc + biome**

Run:
```bash
cd frontend && pnpm exec tsc --noEmit
pnpm exec biome check --write src/features/sar-analysis/lib/sar-activity-display.ts src/features/sar-analysis/lib/sar-activity-display.test.ts src/features/sar-analysis/components/rgroup-table.tsx src/features/sar-analysis/components/rgroup-table.test.tsx src/features/sar-analysis/components/rgroup-heatmap.tsx
pnpm exec biome check src/features/sar-analysis/lib/sar-activity-display.ts src/features/sar-analysis/lib/sar-activity-display.test.ts src/features/sar-analysis/components/rgroup-table.tsx src/features/sar-analysis/components/rgroup-table.test.tsx src/features/sar-analysis/components/rgroup-heatmap.tsx
```
Expected: `tsc` clean (catches the unused `ActivityValue`/`CurveSnapshot` imports if any slip); final `biome check` exit 0.

- [ ] **Step 10: Commit**

```bash
cd /Users/sidx/workspace/chem-vault2
git commit -m "refactor(sar): extract pickReference/potencyShade, kill table->heatmap import

Move the potency ramp to sar-analysis/lib/sar-activity-display; the heatmap
no longer imports helpers from the sibling rgroup-table component, and both
surfaces map curves via activityValueToCurveSnapshot. No behavior change.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>" -- \
  frontend/src/features/sar-analysis/lib/sar-activity-display.ts \
  frontend/src/features/sar-analysis/lib/sar-activity-display.test.ts \
  frontend/src/features/sar-analysis/components/rgroup-table.tsx \
  frontend/src/features/sar-analysis/components/rgroup-table.test.tsx \
  frontend/src/features/sar-analysis/components/rgroup-heatmap.tsx
```

---

## Task 3: `useDecompositionRun` — cancel / isCancelled / runAgain (item 3a)

**Files:**
- Modify: `frontend/src/features/sar-analysis/hooks/use-decomposition-run.ts`
- Test: `frontend/src/features/sar-analysis/hooks/use-decomposition-run.test.tsx`

- [ ] **Step 1: Write the failing tests**

Append to `frontend/src/features/sar-analysis/hooks/use-decomposition-run.test.tsx` (inside the existing `describe`). These cover: `error` no longer reflects a cancel, `cancel()` calls the injected `cancelFn` + flips `isCancelled`, and `runAgain()` re-invokes `startFn`.

```tsx
import { act } from "@testing-library/react";

it("surfaces a cancelled poll via isCancelled, not error", async () => {
  const startFn = vi.fn().mockResolvedValue({ ...READY, status: "running" });
  const pollFn = vi.fn().mockResolvedValue({ ...READY, status: "cancelled" });
  const { result } = renderHook(
    () =>
      useDecompositionRun({
        collectionId: "c1",
        coreSmiles: "c1ccccc1",
        startFn,
        pollFn,
        pollIntervalMs: 5,
      }),
    { wrapper: wrap() },
  );
  await waitFor(() => expect(result.current.isCancelled).toBe(true));
  expect(result.current.error).toBeNull();
  expect(result.current.isPolling).toBe(false);
});

it("cancel() calls cancelFn and flips isCancelled optimistically", async () => {
  const startFn = vi.fn().mockResolvedValue({ ...READY, status: "running" });
  const pollFn = vi.fn().mockResolvedValue({ ...READY, status: "running" });
  const cancelFn = vi.fn().mockResolvedValue({ ...READY, status: "cancelled" });
  const { result } = renderHook(
    () =>
      useDecompositionRun({
        collectionId: "c1",
        coreSmiles: "c1ccccc1",
        startFn,
        pollFn,
        cancelFn,
        pollIntervalMs: 5,
      }),
    { wrapper: wrap() },
  );
  await waitFor(() => expect(result.current.runId).toBe("run-1"));
  act(() => result.current.cancel());
  expect(cancelFn).toHaveBeenCalledWith("run-1");
  await waitFor(() => expect(result.current.isCancelled).toBe(true));
});

it("runAgain() re-starts (a fresh POST) and clears the cancelled flag", async () => {
  const startFn = vi.fn().mockResolvedValue({ ...READY, status: "running" });
  const pollFn = vi.fn().mockResolvedValue({ ...READY, status: "cancelled" });
  const cancelFn = vi.fn().mockResolvedValue({ ...READY, status: "cancelled" });
  const { result } = renderHook(
    () =>
      useDecompositionRun({
        collectionId: "c1",
        coreSmiles: "c1ccccc1",
        startFn,
        pollFn,
        cancelFn,
        pollIntervalMs: 5,
      }),
    { wrapper: wrap() },
  );
  await waitFor(() => expect(result.current.isCancelled).toBe(true));
  act(() => result.current.runAgain());
  await waitFor(() => expect(startFn).toHaveBeenCalledTimes(2));
  expect(result.current.isCancelled).toBe(false);
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && pnpm exec vitest run src/features/sar-analysis/hooks/use-decomposition-run.test.tsx`
Expected: FAIL — `result.current.cancel`/`isCancelled`/`runAgain` are undefined.

- [ ] **Step 3: Implement the cancel trio**

Edit `frontend/src/features/sar-analysis/hooks/use-decomposition-run.ts`:

(a) Imports — add `useCallback`, `useState`:
```ts
import { useCallback, useMemo, useState } from "react";
```

(b) Params type — add `cancelFn`:
```ts
export type UseDecompositionRunParams = {
  collectionId?: string;
  moleculeIds?: string[];
  coreSmiles: string | null;
  startFn?: (input: StartInput) => Promise<DecompositionRunResponse>;
  pollFn?: (runId: string) => Promise<DecompositionRunResponse>;
  cancelFn?: (runId: string) => Promise<DecompositionRunResponse>;
  pollIntervalMs?: number;
  enabled?: boolean;
};
```

(c) Return type — add `isCancelled`, `cancel`, `runAgain`:
```ts
export type UseDecompositionRunReturn = {
  runId: string | null;
  labels: string[];
  counts: { matched: number; unmatched: number; total: number } | null;
  status: string | null;
  isStarting: boolean;
  isPolling: boolean;
  isCancelled: boolean;
  error: Error | null;
  cancel: () => void;
  runAgain: () => void;
};
```

(d) Destructure `cancelFn` (default below) and add nonce + cancelled state; fold the nonce into the key:
```ts
  const {
    collectionId,
    moleculeIds,
    coreSmiles,
    startFn = defaultStartFn,
    pollFn = defaultPollFn,
    cancelFn = defaultCancelFn,
    pollIntervalMs = DEFAULT_POLL_MS,
    enabled = true,
  } = params;

  const [runNonce, setRunNonce] = useState(0);
  const [cancelledRunId, setCancelledRunId] = useState<string | null>(null);

  const sourceKey = collectionId ? `coll:${collectionId}` : `ids:${sortedKey(moleculeIds ?? [])}`;
  const key = `${sourceKey}|core:${coreSmiles ?? ""}|n:${runNonce}`;
```

(e) Capture the raw poll `data` and drop `cancelled` from `getError`:
```ts
  const { result: polled, error: pollError, data: polledData } = useJobPoll<
    DecompositionRunResponse,
    DecompositionRunResponse
  >({
    job,
    pollFn,
    getStatus: (j) => j.status,
    getResult: (j) => (j.status === "ready" ? j : null),
    getError: (j) => (j.status === "failed" ? (j.error_message ?? "decomposition failed") : null),
    pollIntervalMs,
    queryKey: "decomposition-run-poll",
  });
```

(f) Derive cancelled + the callbacks, and return them (note `isPolling` gains `&& !isCancelled`):
```ts
  const ready = polled ?? (startRun?.status === "ready" ? startRun : null);
  const current = ready ?? startRun;
  const runId = startRun?.run_id ?? null;

  const serverCancelled =
    polledData?.status === "cancelled" || startRun?.status === "cancelled";
  const isCancelled = serverCancelled || (cancelledRunId != null && cancelledRunId === runId);

  const cancel = useCallback(() => {
    if (!runId) return;
    setCancelledRunId(runId);
    void cancelFn(runId).catch(() => {});
  }, [runId, cancelFn]);

  const runAgain = useCallback(() => {
    setCancelledRunId(null);
    setRunNonce((n) => n + 1);
  }, []);

  return {
    runId,
    labels: current?.rgroup_labels ?? [],
    counts: current
      ? {
          matched: current.matched_count,
          unmatched: current.unmatched_count,
          total: current.total_count,
        }
      : null,
    status: current?.status ?? null,
    isStarting: start.isPending && queryEnabled,
    isPolling: job != null && ready === null && pollError === null && !isCancelled,
    isCancelled,
    error: (pollError ? new Error(pollError) : null) ?? (start.error as Error | null) ?? null,
    cancel,
    runAgain,
  };
```

(g) Add the default cancel fn next to the other defaults at the bottom:
```ts
async function defaultCancelFn(runId: string): Promise<DecompositionRunResponse> {
  const { cancelDecompositionRunApiV1SarDecompositionJobsRunIdCancelPost } = await import(
    "@/shared/lib/api/sar-analysis/sar-analysis"
  );
  return cancelDecompositionRunApiV1SarDecompositionJobsRunIdCancelPost(
    runId,
  ) as unknown as DecompositionRunResponse;
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend && pnpm exec vitest run src/features/sar-analysis/hooks/use-decomposition-run.test.tsx`
Expected: PASS (original 3 + new 3).

- [ ] **Step 5: tsc + biome**

Run:
```bash
cd frontend && pnpm exec tsc --noEmit
pnpm exec biome check --write src/features/sar-analysis/hooks/use-decomposition-run.ts src/features/sar-analysis/hooks/use-decomposition-run.test.tsx
pnpm exec biome check src/features/sar-analysis/hooks/use-decomposition-run.ts src/features/sar-analysis/hooks/use-decomposition-run.test.tsx
```
Expected: `tsc` clean; final `biome check` exit 0.

- [ ] **Step 6: Commit**

```bash
cd /Users/sidx/workspace/chem-vault2
git commit -m "feat(sar): useDecompositionRun cancel/isCancelled/runAgain

cancel() POSTs the cancel route + flips isCancelled optimistically;
runAgain() bumps a query-key nonce so the start re-POSTs (cache is
READY-only, so the cancelled run is ignored). A user cancel is no longer
folded into error.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>" -- \
  frontend/src/features/sar-analysis/hooks/use-decomposition-run.ts \
  frontend/src/features/sar-analysis/hooks/use-decomposition-run.test.tsx
```

---

## Task 4: `useActivityProjection` — cancel / isCancelled / runAgain (item 3b)

**Files:**
- Modify: `frontend/src/features/sar-analysis/hooks/use-activity-projection.ts`
- Test: `frontend/src/features/sar-analysis/hooks/use-activity-projection.test.tsx`

- [ ] **Step 1: Write the failing tests**

First inspect the existing test for its channel/READY fixtures: `cd frontend && sed -n '1,40p' src/features/sar-analysis/hooks/use-activity-projection.test.tsx` — reuse its existing `wrap()` and a ready projection fixture (the response shape is `{ projection_id, status, error_message }`). Append these three tests inside the existing `describe`, mirroring Task 3 (the projection response uses `projection_id`):

```tsx
import { act } from "@testing-library/react";

const CHANNEL = {
  column: "drc:rd1",
  source: "dr_curve" as const,
  intercept_key: null,
  selection_rule: "latest",
  protocol_id: "p1",
  label: "IC50",
};
const PROJ_RUNNING = { projection_id: "proj-1", status: "running", error_message: null };

it("surfaces a cancelled projection poll via isCancelled, not error", async () => {
  const startFn = vi.fn().mockResolvedValue(PROJ_RUNNING);
  const pollFn = vi.fn().mockResolvedValue({ ...PROJ_RUNNING, status: "cancelled" });
  const { result } = renderHook(
    () =>
      useActivityProjection({
        collectionId: "c1",
        channel: CHANNEL,
        startFn,
        pollFn,
        pollIntervalMs: 5,
      }),
    { wrapper: wrap() },
  );
  await waitFor(() => expect(result.current.isCancelled).toBe(true));
  expect(result.current.error).toBeNull();
  expect(result.current.isPolling).toBe(false);
});

it("cancel() calls cancelFn and flips isCancelled", async () => {
  const startFn = vi.fn().mockResolvedValue(PROJ_RUNNING);
  const pollFn = vi.fn().mockResolvedValue(PROJ_RUNNING);
  const cancelFn = vi.fn().mockResolvedValue({ ...PROJ_RUNNING, status: "cancelled" });
  const { result } = renderHook(
    () =>
      useActivityProjection({
        collectionId: "c1",
        channel: CHANNEL,
        startFn,
        pollFn,
        cancelFn,
        pollIntervalMs: 5,
      }),
    { wrapper: wrap() },
  );
  await waitFor(() => expect(result.current.projectionId).toBe("proj-1"));
  act(() => result.current.cancel());
  expect(cancelFn).toHaveBeenCalledWith("proj-1");
  await waitFor(() => expect(result.current.isCancelled).toBe(true));
});

it("runAgain() re-starts and clears the cancelled flag", async () => {
  const startFn = vi.fn().mockResolvedValue(PROJ_RUNNING);
  const pollFn = vi.fn().mockResolvedValue({ ...PROJ_RUNNING, status: "cancelled" });
  const cancelFn = vi.fn().mockResolvedValue({ ...PROJ_RUNNING, status: "cancelled" });
  const { result } = renderHook(
    () =>
      useActivityProjection({
        collectionId: "c1",
        channel: CHANNEL,
        startFn,
        pollFn,
        cancelFn,
        pollIntervalMs: 5,
      }),
    { wrapper: wrap() },
  );
  await waitFor(() => expect(result.current.isCancelled).toBe(true));
  act(() => result.current.runAgain());
  await waitFor(() => expect(startFn).toHaveBeenCalledTimes(2));
  expect(result.current.isCancelled).toBe(false);
});
```

If the existing test file lacks a `wrap()` helper, copy the one from `use-decomposition-run.test.tsx` (lines 7–12).

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && pnpm exec vitest run src/features/sar-analysis/hooks/use-activity-projection.test.tsx`
Expected: FAIL — `cancel`/`isCancelled`/`runAgain` undefined.

- [ ] **Step 3: Implement the cancel trio** (symmetric to Task 3)

Edit `frontend/src/features/sar-analysis/hooks/use-activity-projection.ts`:

(a) Imports:
```ts
import { useCallback, useMemo, useState } from "react";
```

(b) Params — add `cancelFn`:
```ts
  cancelFn?: (id: string) => Promise<ActivityProjectionResponse>;
```
(add the line inside `UseActivityProjectionParams`, after `pollFn`).

(c) Return type — add the trio:
```ts
export type UseActivityProjectionReturn = {
  projectionId: string | null;
  status: string | null;
  isStarting: boolean;
  isPolling: boolean;
  isCancelled: boolean;
  error: Error | null;
  cancel: () => void;
  runAgain: () => void;
};
```

(d) Destructure `cancelFn` and add nonce/cancelled state; fold the nonce into the start query key:
```ts
  const {
    collectionId,
    moleculeIds,
    channel,
    startFn = defaultStartFn,
    pollFn = defaultPollFn,
    cancelFn = defaultCancelFn,
    pollIntervalMs = DEFAULT_POLL_MS,
    enabled = true,
  } = params;

  const [runNonce, setRunNonce] = useState(0);
  const [cancelledId, setCancelledId] = useState<string | null>(null);
```
and change the start `useQuery` key:
```ts
    queryKey: ["activity-projection", "start", sourceKey, channelKey, runNonce],
```

(e) Capture raw poll `data`, drop `cancelled` from `getError`:
```ts
  const { result: polled, error: pollError, data: polledData } = useJobPoll<
    ActivityProjectionResponse,
    ActivityProjectionResponse
  >({
    job,
    pollFn,
    getStatus: (j) => j.status,
    getResult: (j) => (j.status === "ready" ? j : null),
    getError: (j) =>
      j.status === "failed" ? (j.error_message ?? "activity projection failed") : null,
    pollIntervalMs,
    queryKey: "activity-projection-poll",
  });
```

(f) Derive cancelled + callbacks; return them:
```ts
  const ready = polled ?? (startProj?.status === "ready" ? startProj : null);
  const current = ready ?? startProj;
  const projectionId = startProj?.projection_id ?? null;

  const serverCancelled =
    polledData?.status === "cancelled" || startProj?.status === "cancelled";
  const isCancelled = serverCancelled || (cancelledId != null && cancelledId === projectionId);

  const cancel = useCallback(() => {
    if (!projectionId) return;
    setCancelledId(projectionId);
    void cancelFn(projectionId).catch(() => {});
  }, [projectionId, cancelFn]);

  const runAgain = useCallback(() => {
    setCancelledId(null);
    setRunNonce((n) => n + 1);
  }, []);

  return {
    projectionId,
    status: current?.status ?? null,
    isStarting: start.isPending && queryEnabled,
    isPolling: job != null && ready === null && pollError === null && !isCancelled,
    isCancelled,
    error: (pollError ? new Error(pollError) : null) ?? (start.error as Error | null) ?? null,
    cancel,
    runAgain,
  };
```

(g) Add the default cancel fn at the bottom (mirror the `getActivityProjection…ProjectionIdGet` casing — the cancel fn is `…JobsProjectionIdCancelPost`):
```ts
async function defaultCancelFn(id: string): Promise<ActivityProjectionResponse> {
  const { cancelActivityProjectionApiV1SarActivityProjectionJobsProjectionIdCancelPost } =
    await import("@/shared/lib/api/sar-analysis/sar-analysis");
  return cancelActivityProjectionApiV1SarActivityProjectionJobsProjectionIdCancelPost(
    id,
  ) as unknown as ActivityProjectionResponse;
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend && pnpm exec vitest run src/features/sar-analysis/hooks/use-activity-projection.test.tsx`
Expected: PASS.

- [ ] **Step 5: tsc + biome**

Run:
```bash
cd frontend && pnpm exec tsc --noEmit
pnpm exec biome check --write src/features/sar-analysis/hooks/use-activity-projection.ts src/features/sar-analysis/hooks/use-activity-projection.test.tsx
pnpm exec biome check src/features/sar-analysis/hooks/use-activity-projection.ts src/features/sar-analysis/hooks/use-activity-projection.test.tsx
```
Expected: `tsc` clean; final `biome check` exit 0.

- [ ] **Step 6: Commit**

```bash
cd /Users/sidx/workspace/chem-vault2
git commit -m "feat(sar): useActivityProjection cancel/isCancelled/runAgain

Symmetric to useDecompositionRun: cancel() POSTs the projection cancel
route + flips isCancelled; runAgain() bumps the start key nonce; a user
cancel is no longer folded into error.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>" -- \
  frontend/src/features/sar-analysis/hooks/use-activity-projection.ts \
  frontend/src/features/sar-analysis/hooks/use-activity-projection.test.tsx
```

---

## Task 5: `SarView` — honest cancel / empty / projection-failed states (item 3c)

**Files:**
- Modify: `frontend/src/features/sar-analysis/components/sar-view.tsx`
- Test: `frontend/src/features/sar-analysis/components/sar-view.test.tsx`

- [ ] **Step 1: Extend the test mock types + constants**

In `frontend/src/features/sar-analysis/components/sar-view.test.tsx`, add the new fields to the `RunReturn`/`ProjReturn` types and the `READY_RUN`/`READY_PROJ` constants so the mocked hook return matches the new hook API:

```tsx
type RunReturn = {
  runId: string | null;
  labels: string[];
  counts: { matched: number; unmatched: number; total: number } | null;
  status: string | null;
  isStarting: boolean;
  isPolling: boolean;
  isCancelled: boolean;
  error: Error | null;
  cancel: () => void;
  runAgain: () => void;
};
type ProjReturn = {
  projectionId: string | null;
  status: string | null;
  isStarting: boolean;
  isPolling: boolean;
  isCancelled: boolean;
  error: Error | null;
  cancel: () => void;
  runAgain: () => void;
};

const READY_RUN: RunReturn = {
  runId: "run-1",
  labels: ["R1", "R2"],
  counts: { matched: 8, unmatched: 2, total: 10 },
  status: "ready",
  isStarting: false,
  isPolling: false,
  isCancelled: false,
  error: null,
  cancel: vi.fn(),
  runAgain: vi.fn(),
};
const READY_PROJ: ProjReturn = {
  projectionId: "proj-1",
  status: "ready",
  isStarting: false,
  isPolling: false,
  isCancelled: false,
  error: null,
  cancel: vi.fn(),
  runAgain: vi.fn(),
};
```

- [ ] **Step 2: Write the failing tests**

Append these to the `describe("SarView (server orchestration)", …)` block:

```tsx
it("shows a Cancel affordance while decomposing and calls run.cancel", () => {
  const cancel = vi.fn();
  runReturn = { ...READY_RUN, runId: "run-1", status: "running", isPolling: true, cancel };
  renderSarView();
  fireEvent.click(screen.getByRole("button", { name: "Cancel decomposition" }));
  expect(cancel).toHaveBeenCalled();
});

it("shows a neutral cancelled state with Run again", () => {
  const runAgain = vi.fn();
  runReturn = { ...READY_RUN, status: "cancelled", isCancelled: true, runAgain };
  renderSarView();
  expect(screen.getByText("Decomposition cancelled")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Run decomposition again" }));
  expect(runAgain).toHaveBeenCalled();
});

it("surfaces a decomposition failure with Try again", () => {
  runReturn = { ...READY_RUN, status: "failed", error: new Error("bad core") };
  renderSarView();
  expect(screen.getByText(/Decomposition failed: bad core/)).toBeInTheDocument();
});

it("surfaces an activity-projection failure (table still renders)", () => {
  projReturn = { ...READY_PROJ, status: "failed", error: new Error("no data") };
  renderSarView();
  fireEvent.click(screen.getByTestId("set-color-spec"));
  expect(screen.getByText(/Activity computation failed: no data/)).toBeInTheDocument();
  expect(screen.getByTestId("rgroup-table")).toBeInTheDocument();
});

it("shows a no-match empty state instead of an empty grid", () => {
  runReturn = { ...READY_RUN, counts: { matched: 0, unmatched: 10, total: 10 } };
  renderSarView();
  expect(screen.getByText("No compounds matched this core. Try a different scaffold.")).toBeInTheDocument();
  expect(screen.queryByTestId("rgroup-table")).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Heatmap view" })).not.toBeInTheDocument();
});
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd frontend && pnpm exec vitest run src/features/sar-analysis/components/sar-view.test.tsx`
Expected: FAIL — new copy/roles/empty-state not present; type errors gone after Step 1.

- [ ] **Step 4: Implement the state taxonomy in `sar-view.tsx`**

In `frontend/src/features/sar-analysis/components/sar-view.tsx`:

(a) After the existing `const showHeatmap = …` line (~55), add the match-state derivations:
```tsx
  const matched = run.counts?.matched ?? 0;
  const hasMatches = ready && run.runId != null && matched > 0;
  const noMatches = ready && run.runId != null && matched === 0;
```

(b) Replace the current progress/error block (lines ~76–84) with the full decomposition + activity lanes:
```tsx
      {(run.isStarting || run.isPolling) && (
        <p className="flex items-center gap-2 text-xs text-muted-foreground">
          Decomposing…
          <button
            type="button"
            aria-label="Cancel decomposition"
            className="underline underline-offset-2 hover:text-foreground"
            onClick={run.cancel}
          >
            Cancel
          </button>
        </p>
      )}
      {run.isCancelled && (
        <p className="flex items-center gap-2 text-xs text-muted-foreground">
          Decomposition cancelled
          <button
            type="button"
            aria-label="Run decomposition again"
            className="underline underline-offset-2 hover:text-foreground"
            onClick={run.runAgain}
          >
            Run again
          </button>
        </p>
      )}
      {run.error && (
        <p className="flex items-center gap-2 text-xs text-destructive">
          Decomposition failed: {run.error.message}
          <button
            type="button"
            aria-label="Try decomposition again"
            className="underline underline-offset-2 hover:opacity-80"
            onClick={run.runAgain}
          >
            Try again
          </button>
        </p>
      )}

      {colorSpec != null && (projection.isStarting || projection.isPolling) && (
        <p className="flex items-center gap-2 text-xs text-muted-foreground">
          Computing activity…
          <button
            type="button"
            aria-label="Cancel activity computation"
            className="underline underline-offset-2 hover:text-foreground"
            onClick={projection.cancel}
          >
            Cancel
          </button>
        </p>
      )}
      {colorSpec != null && projection.isCancelled && (
        <p className="flex items-center gap-2 text-xs text-muted-foreground">
          Activity computation cancelled
          <button
            type="button"
            aria-label="Run activity computation again"
            className="underline underline-offset-2 hover:text-foreground"
            onClick={projection.runAgain}
          >
            Run again
          </button>
        </p>
      )}
      {colorSpec != null && projection.error && (
        <p className="flex items-center gap-2 text-xs text-destructive">
          Activity computation failed: {projection.error.message}
          <button
            type="button"
            aria-label="Try activity computation again"
            className="underline underline-offset-2 hover:opacity-80"
            onClick={projection.runAgain}
          >
            Try again
          </button>
        </p>
      )}
```

(c) Gate the view toggle on `hasMatches` (was `ready`) — change `{ready && (` (the `role="group"` toggle block, ~line 86) to:
```tsx
      {hasMatches && (
```

(d) Leave the count banner as-is (`{ready && run.runId && (` … "M matched of N (U unmatched)") — it stays honest at 0.

(e) Add the no-match panel immediately after the count banner block:
```tsx
      {noMatches && (
        <p className="text-xs text-muted-foreground">
          No compounds matched this core. Try a different scaffold.
        </p>
      )}
```

(f) Gate the table/heatmap render on `hasMatches` — change `{ready &&\n        run.runId &&\n        (showHeatmap && …` (~line 126) to start with `{hasMatches &&`:
```tsx
      {hasMatches &&
        (showHeatmap && colorSpec && projection.projectionId ? (
          <RGroupHeatmap
            runId={run.runId}
            projectionId={projection.projectionId}
            labels={run.labels}
            colorSpec={colorSpec}
          />
        ) : (
          <RGroupTable
            runId={run.runId}
            projectionId={projectionReady ? projection.projectionId : null}
            labels={run.labels}
            colorSpec={colorSpec}
            matchedCount={run.counts?.matched}
            onSaveSelection={(rows) => setSaveIntent({ mode: "selection", rows })}
            onSaveAll={({ count, filter, projectionId }) =>
              setSaveIntent({ mode: "all", count, filter, projectionId })
            }
          />
        ))}
```
(`run.runId` is non-null whenever `hasMatches` is true; TS already narrows via the `RGroupTable`/`RGroupHeatmap` `runId: string` prop — if tsc complains, keep the existing `run.runId &&` guard inside, i.e. `{hasMatches && run.runId && (…`).

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd frontend && pnpm exec vitest run src/features/sar-analysis/components/sar-view.test.tsx`
Expected: PASS (original 7 + new 5). The existing "hides the sub-toggle while pending" test still passes (it sets `isPolling: true`, `runId: null` → `Decomposing…` + Cancel both present; the toggle stays hidden).

- [ ] **Step 6: tsc + biome**

Run:
```bash
cd frontend && pnpm exec tsc --noEmit
pnpm exec biome check --write src/features/sar-analysis/components/sar-view.tsx src/features/sar-analysis/components/sar-view.test.tsx
pnpm exec biome check src/features/sar-analysis/components/sar-view.tsx src/features/sar-analysis/components/sar-view.test.tsx
```
Expected: `tsc` clean; final `biome check` exit 0. (a11y: the new `<button>`s carry `type="button"` + `aria-label`.)

- [ ] **Step 7: Commit**

```bash
cd /Users/sidx/workspace/chem-vault2
git commit -m "feat(sar): honest cancel/empty/projection-failed states in SarView

Inline Cancel on both progress lines; neutral cancelled + Run again;
surface activity-projection failures (table still renders); 0-match shows
'try a different scaffold' instead of an empty grid (toggle hidden).

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>" -- \
  frontend/src/features/sar-analysis/components/sar-view.tsx \
  frontend/src/features/sar-analysis/components/sar-view.test.tsx
```

---

## Task 6: Domain-model aggregate note (item 4)

**Files:**
- Modify: `docs/domain-model/04-sar-analysis.md`

- [ ] **Step 1: Read the file to find the insertion point**

Run: `cd /Users/sidx/workspace/chem-vault2 && sed -n '1,60p' docs/domain-model/04-sar-analysis.md` and skim the section headings (`grep -n '^#' docs/domain-model/04-sar-analysis.md`). Insert the new section after the fingerprint/Markush aggregate sections (before any "open questions"/"deviations"/footer), so it reads as an addition to the aggregate catalog.

- [ ] **Step 2: Add the section**

Insert this markdown (verbatim):

```markdown
## Async-job / read-model aggregates (Part 1b/2 additions)

Two aggregates were added when the SAR workbench moved its compute server-side.
They are **derived read models behind async jobs**, not registration state — they
hold no chemistry of record, only cached projections over already-registered
molecules. Both share an async-job lifecycle: `pending → running →
ready | failed | cancelled`.

### RGroupDecompositionRun

- **Purpose:** one R-group decomposition of a molecule set against a chosen core.
- **Identity / cache key:** `membership_hash` (fold over the scoped member set) +
  `core_hash` (canonical core SMILES). A `find_cached` lookup returns a prior run
  only when it is `READY`, so a `failed`/`cancelled` run is never reused and a
  re-request starts fresh.
- **State:** `status`, `rgroup_labels`, and `matched / unmatched / total` counts.
- **Read model:** `RGroupAssignment` rows (one per matched molecule, the R-group
  fragment SMILES per label) are what the `/decomposition/{run_id}/rows` and
  `/heatmap` endpoints page, sort, filter, and aggregate over.

### SarActivityProjection

- **Purpose:** project a single activity channel (a DR intercept or a raw readout,
  under a selection rule) onto a molecule set, so the table/heatmap can colour by
  potency without recomputing per render.
- **Identity / cache key:** `membership_hash` + `channel_hash` (the semantic
  channel fields). `READY`-only cache hits, same as the decomposition run.
- **State:** `status` + `ActivityScalar` values keyed by molecule id.
- **Consumed by:** the table activity column and the heatmap cell colouring,
  joined to the decomposition rows by molecule id at query time.

### Relationship to the existing aggregates

`MolecularFingerprint` and `MarkushDefinition` remain the SAR registration-side
aggregates. `RGroupDecompositionRun` and `SarActivityProjection` sit beside them
as compute artifacts layered on registered molecules — they can be dropped and
recomputed at any time without data loss.
```

- [ ] **Step 3: Verify tracking, then commit** (`docs/` is gitignored)

Run: `cd /Users/sidx/workspace/chem-vault2 && git ls-files docs/domain-model/04-sar-analysis.md`
- If it prints the path → tracked; commit normally.
- If it prints nothing → `git add -f docs/domain-model/04-sar-analysis.md` first.

```bash
cd /Users/sidx/workspace/chem-vault2
git add -f docs/domain-model/04-sar-analysis.md
git commit -m "docs(sar): document RGroupDecompositionRun + SarActivityProjection aggregates

Add the async-job/read-model aggregates (lifecycle, membership/core/channel
hashes as READY-only cache identity, RGroupAssignment/ActivityScalar read
models, relationship to fingerprint/Markush) — closes the domain-model drift.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>" -- \
  docs/domain-model/04-sar-analysis.md
```

---

## Final verification

- [ ] **Run the full set of touched tests**

```bash
cd frontend && pnpm exec vitest run \
  src/features/research-organization/lib/activity-curve-snapshot.test.ts \
  src/features/research-organization/components/search/dose-response-cell.test.tsx \
  src/features/sar-analysis/lib/sar-activity-display.test.ts \
  src/features/sar-analysis/components/rgroup-table.test.tsx \
  src/features/sar-analysis/components/rgroup-heatmap.test.tsx \
  src/features/sar-analysis/hooks/use-decomposition-run.test.tsx \
  src/features/sar-analysis/hooks/use-activity-projection.test.tsx \
  src/features/sar-analysis/components/sar-view.test.tsx
pnpm exec tsc --noEmit
```
Expected: all green, tsc clean.

- [ ] **Confirm the smell is gone**

Run: `cd frontend && grep -rn 'from "./rgroup-table"' src/features/sar-analysis/components/rgroup-heatmap.tsx`
Expected: no output (heatmap no longer imports from the table component).

- [ ] **Update `docs/superpowers/specs/2026-06-15-sar-unit-c-handoff.md`** — mark items 3, 4, 5 done with the commit hashes (force-add if needed), so the handoff reflects reality for item 6/7 later.

---

## Self-review notes

- **Spec coverage:** item 3 → Tasks 3/4/5 (hooks + view, all six states + cancel); item 4 → Task 6; item 5 → Tasks 1/2 (mapper + potency, both consumers rewired). All spec sections map to a task.
- **Type consistency:** the hook return adds exactly `isCancelled: boolean`, `cancel: () => void`, `runAgain: () => void` in both hooks and the sar-view mock types; `activityValueToCurveSnapshot` signature is identical to the old `snapshotFromActivity`; `pickReference`/`potencyShade` signatures unchanged.
- **No placeholders:** every code/test/command step is concrete. The only judgement call (keep `run.runId &&` inside the `hasMatches` render if tsc narrows differently) is spelled out in Task 5 Step 4(f).
- **Order:** 1→2 (item 5; mapper before its consumers) → 3→4 (hooks) → 5 (view, depends on 3/4) → 6 (docs, independent).
```
