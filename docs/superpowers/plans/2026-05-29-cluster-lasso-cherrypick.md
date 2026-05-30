# Cluster-map lasso → cherry-pick basket — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the collections Cluster-map lasso a real cherry-pick tool: reliably select compounds under the drag, accumulate a persistent diverse purchase basket region-by-region, and commit it to a collection.

**Architecture:** Frontend-only. Fix the lasso by wiring the already-built-but-unused `lasso-math` point-in-polygon to Plotly's `ev.lassoPoints` (robust on both `scatter` and `scattergl`). Add a localStorage-backed basket hook, a region diverse-pick hook that reuses the existing UMAP endpoint, two small presentational bars, basket/candidate map markers, and orchestrate it all in `cluster-map-view.tsx`. No backend changes, no new tables.

**Tech Stack:** Next.js 16 / React 19 / TypeScript / TanStack Query v5 / Plotly.js / vitest + @testing-library/react. Spec: `docs/superpowers/specs/2026-05-29-cluster-lasso-cherrypick-design.md`.

**Commands:**
- Single test file: `cd frontend && pnpm vitest run src/features/sar-analysis/<path>.test.tsx`
- Typecheck: `cd frontend && pnpm exec tsc --noEmit`
- Lint: `cd frontend && pnpm lint`

---

## File Structure

**New files (frontend):**
- `src/features/sar-analysis/hooks/use-cherrypick-basket.ts` — localStorage-backed basket `Set`, keyed per collection. SSR-safe.
- `src/features/sar-analysis/hooks/use-cherrypick-basket.test.ts`
- `src/features/sar-analysis/hooks/use-region-diverse-pick.ts` — on-demand MaxMin over a lassoed subset, wrapping `useUmapCluster`.
- `src/features/sar-analysis/hooks/use-region-diverse-pick.test.tsx`
- `src/features/sar-analysis/components/region-action-bar.tsx` — region selection action bar (presentational).
- `src/features/sar-analysis/components/region-action-bar.test.tsx`
- `src/features/sar-analysis/components/cluster-basket-bar.tsx` — basket count + plate hint + Save / Clear / Add-picks (presentational).
- `src/features/sar-analysis/components/cluster-basket-bar.test.tsx`
- `src/features/sar-analysis/lib/cluster-overlay.ts` — pure builder for the in-basket + region-candidate map traces.
- `src/features/sar-analysis/lib/cluster-overlay.test.ts`

**Modified files (frontend):**
- `src/features/sar-analysis/lib/lasso-math.ts` — add `selectedIdsFromPlotlyEvent`.
- `src/features/sar-analysis/lib/lasso-math.test.ts` — add tests for the new export.
- `src/features/sar-analysis/components/cluster-scatter.tsx` — wire the polygon selection; render overlay traces; accept `basketIds` / `regionPickIds`.
- `src/features/sar-analysis/components/cluster-toolbar.tsx` — drop the `Save selection` button + `onSave`/`selectedCount` props (moves to the basket bar).
- `src/features/sar-analysis/components/cluster-toolbar.test.tsx` — drop the Save assertions.
- `src/features/sar-analysis/components/cluster-selection-pane.tsx` — render the basket (header + count) instead of an abstract selection.
- `src/features/sar-analysis/components/cluster-selection-pane.test.tsx` — update for the basket prop (create if missing).
- `src/features/sar-analysis/components/cluster-map-view.tsx` — integrate basket + region hooks + the two bars + markers; decouple Diversify from the lasso.
- `src/features/sar-analysis/components/cluster-map-view.test.tsx` — update mocks + add basket-flow tests.

---

### Task 1: Fix the lasso — wire point-in-polygon to the Plotly selection event

The lasso "does nothing" because `cluster-scatter.tsx` resolves selections via the fragile `ev.points` / `pointNumber` path. `lasso-math.ts` already has a tested `idsInsidePolygon` but is never imported. Add an adapter that reads Plotly's data-space `ev.lassoPoints` (lasso) / `ev.range` (box), falls back to `ev.points`, and wire it in.

**Files:**
- Modify: `src/features/sar-analysis/lib/lasso-math.ts`
- Test: `src/features/sar-analysis/lib/lasso-math.test.ts`
- Modify: `src/features/sar-analysis/components/cluster-scatter.tsx:185-199`

- [ ] **Step 1: Write the failing test**

Append to `src/features/sar-analysis/lib/lasso-math.test.ts` (keep existing tests):

```typescript
import { selectedIdsFromPlotlyEvent } from "./lasso-math";

describe("selectedIdsFromPlotlyEvent", () => {
  const points = [
    { moleculeId: "a", x: 0, y: 0 },
    { moleculeId: "b", x: 10, y: 10 },
  ];

  it("resolves ids from a lasso polygon (lassoPoints, data space)", () => {
    const ev = { lassoPoints: { x: [-1, 1, 1, -1], y: [-1, -1, 1, 1] } };
    expect(selectedIdsFromPlotlyEvent(ev, points)).toEqual(["a"]);
  });

  it("resolves ids from a box selection (range corners)", () => {
    const ev = { range: { x: [-1, 1], y: [-1, 1] } };
    expect(selectedIdsFromPlotlyEvent(ev, points)).toEqual(["a"]);
  });

  it("falls back to pointNumber indexing on the base trace", () => {
    const ev = { points: [{ curveNumber: 0, pointNumber: 1 }] };
    expect(selectedIdsFromPlotlyEvent(ev, points)).toEqual(["b"]);
  });

  it("ignores non-base-trace points in the fallback path", () => {
    const ev = { points: [{ curveNumber: 1, pointNumber: 0 }] };
    expect(selectedIdsFromPlotlyEvent(ev, points)).toEqual([]);
  });

  it("returns [] for null / empty event", () => {
    expect(selectedIdsFromPlotlyEvent(null, points)).toEqual([]);
    expect(selectedIdsFromPlotlyEvent({}, points)).toEqual([]);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && pnpm vitest run src/features/sar-analysis/lib/lasso-math.test.ts`
Expected: FAIL — `selectedIdsFromPlotlyEvent is not a function`.

- [ ] **Step 3: Add the adapter to `lasso-math.ts`**

Append to `src/features/sar-analysis/lib/lasso-math.ts`:

```typescript
export interface PlotlySelectionEvent {
  /** Lasso drag: polygon vertices in DATA coordinates. */
  lassoPoints?: { x: number[]; y: number[] };
  /** Box select: [x0, x1] / [y0, y1] in DATA coordinates. */
  range?: { x: number[]; y: number[] };
  /** Per-point selection payload (fragile on scattergl — fallback only). */
  points?: { curveNumber?: number; pointNumber?: number; pointIndex?: number }[];
}

/**
 * Resolve the molecule ids a Plotly lasso/box selection covers.
 *
 * Prefers the data-space geometry (`lassoPoints` / `range`) and tests membership
 * against our own `points` via ray-casting — this is robust on BOTH `scatter`
 * and `scattergl`, where Plotly's per-point `pointNumber` / `customdata` plumbing
 * is historically unreliable. Falls back to `pointNumber` indexing only when no
 * geometry is present.
 */
export function selectedIdsFromPlotlyEvent(
  ev: PlotlySelectionEvent | null | undefined,
  points: IdPoint[],
): string[] {
  if (!ev) return [];

  if (ev.lassoPoints?.x && ev.lassoPoints.x.length >= 3) {
    const lx = ev.lassoPoints.x;
    const ly = ev.lassoPoints.y;
    const poly = lx.map((x, i) => ({ x, y: ly[i] }));
    return idsInsidePolygon(points, poly);
  }

  if (ev.range?.x && ev.range?.y) {
    const [x0, x1] = ev.range.x;
    const [y0, y1] = ev.range.y;
    const poly = [
      { x: x0, y: y0 },
      { x: x1, y: y0 },
      { x: x1, y: y1 },
      { x: x0, y: y1 },
    ];
    return idsInsidePolygon(points, poly);
  }

  if (Array.isArray(ev.points) && ev.points.length > 0) {
    return ev.points
      .filter((p) => (p.curveNumber ?? 0) === 0)
      .map((p) => {
        const idx = p.pointNumber ?? p.pointIndex;
        return typeof idx === "number" ? points[idx]?.moleculeId : undefined;
      })
      .filter((id): id is string => Boolean(id));
  }

  return [];
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && pnpm vitest run src/features/sar-analysis/lib/lasso-math.test.ts`
Expected: PASS (all, including the pre-existing polygon tests).

- [ ] **Step 5: Wire it into `cluster-scatter.tsx`**

In `src/features/sar-analysis/components/cluster-scatter.tsx`, add the import near the top (after the existing imports):

```typescript
import { selectedIdsFromPlotlyEvent } from "@/features/sar-analysis/lib/lasso-math";
```

Replace the `onSelected` handler body (currently `cluster-scatter.tsx:185-199`) with:

```typescript
    onSelected: (ev: any) => {
      // Resolve via data-space geometry (robust on scatter + scattergl).
      const ids = selectedIdsFromPlotlyEvent(ev, points);
      onSelected(ids.length > 0 ? ids : null);
    },
```

- [ ] **Step 6: Verify the existing scatter test still passes**

Run: `cd frontend && pnpm vitest run src/features/sar-analysis/components/cluster-scatter.test.tsx`
Expected: PASS (no regression).

- [ ] **Step 7: Commit**

```bash
git add frontend/src/features/sar-analysis/lib/lasso-math.ts \
        frontend/src/features/sar-analysis/lib/lasso-math.test.ts \
        frontend/src/features/sar-analysis/components/cluster-scatter.tsx
git commit -m "fix(sar_analysis): lasso resolves ids via data-space polygon (scatter + scattergl)"
```

---

### Task 2: `useCherrypickBasket` — localStorage-backed basket Set, per collection

**Files:**
- Create: `src/features/sar-analysis/hooks/use-cherrypick-basket.ts`
- Test: `src/features/sar-analysis/hooks/use-cherrypick-basket.test.ts`

- [ ] **Step 1: Write the failing test**

Create `src/features/sar-analysis/hooks/use-cherrypick-basket.test.ts`:

```typescript
import { renderHook, act } from "@testing-library/react";
import { describe, expect, it, beforeEach } from "vitest";
import { useCherrypickBasket } from "./use-cherrypick-basket";

describe("useCherrypickBasket", () => {
  beforeEach(() => window.localStorage.clear());

  it("starts empty", () => {
    const { result } = renderHook(() => useCherrypickBasket("col-1"));
    expect(result.current.size).toBe(0);
    expect([...result.current.ids]).toEqual([]);
  });

  it("add accumulates and addMany de-dupes overlaps", () => {
    const { result } = renderHook(() => useCherrypickBasket("col-1"));
    act(() => result.current.add("a"));
    act(() => result.current.addMany(["a", "b", "c"]));
    expect(result.current.size).toBe(3);
    expect(result.current.has("b")).toBe(true);
  });

  it("remove and removeMany take ids out", () => {
    const { result } = renderHook(() => useCherrypickBasket("col-1"));
    act(() => result.current.addMany(["a", "b", "c"]));
    act(() => result.current.remove("a"));
    act(() => result.current.removeMany(["b"]));
    expect([...result.current.ids]).toEqual(["c"]);
  });

  it("clear empties the basket", () => {
    const { result } = renderHook(() => useCherrypickBasket("col-1"));
    act(() => result.current.addMany(["a", "b"]));
    act(() => result.current.clear());
    expect(result.current.size).toBe(0);
  });

  it("persists across remounts (localStorage round-trip)", () => {
    const first = renderHook(() => useCherrypickBasket("col-1"));
    act(() => first.result.current.addMany(["a", "b"]));
    first.unmount();
    const second = renderHook(() => useCherrypickBasket("col-1"));
    expect([...second.result.current.ids].sort()).toEqual(["a", "b"]);
  });

  it("keys the basket per collection", () => {
    const a = renderHook(() => useCherrypickBasket("col-1"));
    act(() => a.result.current.add("x"));
    const b = renderHook(() => useCherrypickBasket("col-2"));
    expect(b.result.current.size).toBe(0);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && pnpm vitest run src/features/sar-analysis/hooks/use-cherrypick-basket.test.ts`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement the hook**

Create `src/features/sar-analysis/hooks/use-cherrypick-basket.ts`:

```typescript
"use client";

import { useCallback, useEffect, useState } from "react";

const KEY_PREFIX = "cellar:cherrypick:";

function storageKey(collectionId?: string): string {
  return `${KEY_PREFIX}${collectionId ?? "_search"}`;
}

function readStored(key: string): string[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = window.localStorage.getItem(key);
    const parsed = raw ? JSON.parse(raw) : [];
    return Array.isArray(parsed) ? parsed.filter((x) => typeof x === "string") : [];
  } catch {
    return [];
  }
}

function writeStored(key: string, ids: Set<string>): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(key, JSON.stringify([...ids]));
  } catch {
    // Storage unavailable / quota — basket stays in-memory only.
  }
}

export interface CherrypickBasket {
  ids: Set<string>;
  size: number;
  has: (id: string) => boolean;
  add: (id: string) => void;
  addMany: (ids: string[]) => void;
  remove: (id: string) => void;
  removeMany: (ids: string[]) => void;
  clear: () => void;
}

/**
 * A cherry-pick basket: an accumulating Set of molecule ids, persisted to
 * localStorage under `cellar:cherrypick:{collectionId}`. Survives reload +
 * navigation, scoped to this browser. SSR-safe (no window → in-memory only).
 */
export function useCherrypickBasket(collectionId?: string): CherrypickBasket {
  const key = storageKey(collectionId);
  const [ids, setIds] = useState<Set<string>>(() => new Set(readStored(key)));

  // Re-load when the collection (and therefore the key) changes.
  useEffect(() => {
    setIds(new Set(readStored(key)));
  }, [key]);

  const mutate = useCallback(
    (fn: (prev: Set<string>) => Set<string>) => {
      setIds((prev) => {
        const next = fn(prev);
        writeStored(key, next);
        return next;
      });
    },
    [key],
  );

  const add = useCallback(
    (id: string) => mutate((p) => new Set(p).add(id)),
    [mutate],
  );
  const addMany = useCallback(
    (arr: string[]) =>
      mutate((p) => {
        const next = new Set(p);
        for (const id of arr) next.add(id);
        return next;
      }),
    [mutate],
  );
  const remove = useCallback(
    (id: string) =>
      mutate((p) => {
        const next = new Set(p);
        next.delete(id);
        return next;
      }),
    [mutate],
  );
  const removeMany = useCallback(
    (arr: string[]) =>
      mutate((p) => {
        const next = new Set(p);
        for (const id of arr) next.delete(id);
        return next;
      }),
    [mutate],
  );
  const clear = useCallback(() => mutate(() => new Set()), [mutate]);
  const has = useCallback((id: string) => ids.has(id), [ids]);

  return { ids, size: ids.size, has, add, addMany, remove, removeMany, clear };
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && pnpm vitest run src/features/sar-analysis/hooks/use-cherrypick-basket.test.ts`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/features/sar-analysis/hooks/use-cherrypick-basket.ts \
        frontend/src/features/sar-analysis/hooks/use-cherrypick-basket.test.ts
git commit -m "feat(sar_analysis): useCherrypickBasket — localStorage basket Set, per collection"
```

---

### Task 3: `useRegionDiversePick` — MaxMin over a lassoed subset

Reuses `useUmapCluster` (which already handles inline + async-poll) scoped to the lassoed ids, returning only the representative ids. No new endpoint.

**Files:**
- Create: `src/features/sar-analysis/hooks/use-region-diverse-pick.ts`
- Test: `src/features/sar-analysis/hooks/use-region-diverse-pick.test.tsx`

- [ ] **Step 1: Write the failing test**

Create `src/features/sar-analysis/hooks/use-region-diverse-pick.test.tsx`:

```typescript
import { describe, it, expect, vi } from "vitest";
import { renderHook, act, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import React from "react";
import { useRegionDiversePick } from "./use-region-diverse-pick";

const wrapper = ({ children }: { children: React.ReactNode }) => {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
};

const resultDto = {
  points: [
    { molecule_id: "a", x: 0, y: 0 },
    { molecule_id: "b", x: 1, y: 1 },
  ],
  clusters: [
    { molecule_id: "a", cluster_id: 0 },
    { molecule_id: "b", cluster_id: 0 },
  ],
  representatives: [{ molecule_id: "a", cluster_id: 0 }],
  cluster_count: 1,
  picker: "maxmin",
  picker_params: { n: 1 },
  skipped_molecule_ids: [],
};

describe("useRegionDiversePick", () => {
  it("is idle until pick() is called", () => {
    const startFn = vi.fn();
    const { result } = renderHook(() => useRegionDiversePick({ startFn }), {
      wrapper,
    });
    expect(result.current.active).toBe(false);
    expect(result.current.pickedIds.size).toBe(0);
    expect(startFn).not.toHaveBeenCalled();
  });

  it("pick() runs MaxMin over the subset and returns representative ids", async () => {
    const startFn = vi.fn(async () => ({ result: resultDto, job: null }));
    const { result } = renderHook(() => useRegionDiversePick({ startFn }), {
      wrapper,
    });

    act(() => result.current.pick(["a", "b"], 1));

    await waitFor(() => expect(result.current.pickedIds.size).toBe(1));
    expect([...result.current.pickedIds]).toEqual(["a"]);

    const call = startFn.mock.calls[0][0];
    expect(call.picker).toBe("maxmin");
    expect(call.molecule_ids).toEqual(["a", "b"]);
    expect(call.n).toBe(1);
  });

  it("reset() clears the picks and goes idle", async () => {
    const startFn = vi.fn(async () => ({ result: resultDto, job: null }));
    const { result } = renderHook(() => useRegionDiversePick({ startFn }), {
      wrapper,
    });
    act(() => result.current.pick(["a", "b"], 1));
    await waitFor(() => expect(result.current.pickedIds.size).toBe(1));
    act(() => result.current.reset());
    expect(result.current.active).toBe(false);
    expect(result.current.pickedIds.size).toBe(0);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && pnpm vitest run src/features/sar-analysis/hooks/use-region-diverse-pick.test.tsx`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement the hook**

Create `src/features/sar-analysis/hooks/use-region-diverse-pick.ts`:

```typescript
"use client";

import { useCallback, useMemo, useState } from "react";

import { useUmapCluster, type UseUmapClusterInput } from "./use-umap-cluster";

export interface UseRegionDiversePickOptions {
  /** Test override forwarded to useUmapCluster. */
  startFn?: UseUmapClusterInput["startFn"];
  /** Test override forwarded to useUmapCluster. */
  pollFn?: UseUmapClusterInput["pollFn"];
}

export interface RegionDiversePick {
  /** Representative ids of the last pick. Empty while loading or idle. */
  pickedIds: Set<string>;
  loading: boolean;
  error: string | null;
  /** True once pick() has been called and not reset. */
  active: boolean;
  /** Run MaxMin over `ids`, selecting `n` diverse representatives. */
  pick: (ids: string[], n: number) => void;
  reset: () => void;
}

/**
 * On-demand MaxMin diversity pick over a lassoed subset. Wraps useUmapCluster
 * (which handles inline + async-poll) and surfaces only the representative ids.
 * The throwaway embedding of a small lasso region is cheap; we ignore the coords.
 */
export function useRegionDiversePick(
  opts: UseRegionDiversePickOptions = {},
): RegionDiversePick {
  const [request, setRequest] = useState<{ ids: string[]; n: number } | null>(
    null,
  );

  const { result, loading, error } = useUmapCluster({
    moleculeIds: request?.ids,
    picker: "maxmin",
    n: request?.n,
    enabled: request !== null && (request?.ids.length ?? 0) > 0,
    startFn: opts.startFn,
    pollFn: opts.pollFn,
  });

  const pickedIds = useMemo(
    () => new Set((result?.representatives ?? []).map((r) => r.moleculeId)),
    [result],
  );

  const pick = useCallback(
    (ids: string[], n: number) => setRequest({ ids, n }),
    [],
  );
  const reset = useCallback(() => setRequest(null), []);

  return {
    pickedIds,
    loading: request !== null && loading,
    error,
    active: request !== null,
    pick,
    reset,
  };
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && pnpm vitest run src/features/sar-analysis/hooks/use-region-diverse-pick.test.tsx`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/features/sar-analysis/hooks/use-region-diverse-pick.ts \
        frontend/src/features/sar-analysis/hooks/use-region-diverse-pick.test.tsx
git commit -m "feat(sar_analysis): useRegionDiversePick — MaxMin over a lassoed subset"
```

---

### Task 4: `RegionActionBar` — region selection action bar

Presentational. Appears when a lasso is active. The parent owns all state; this just renders.

**Files:**
- Create: `src/features/sar-analysis/components/region-action-bar.tsx`
- Test: `src/features/sar-analysis/components/region-action-bar.test.tsx`

- [ ] **Step 1: Write the failing test**

Create `src/features/sar-analysis/components/region-action-bar.test.tsx`:

```typescript
import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { RegionActionBar } from "./region-action-bar";

const baseProps = {
  regionCount: 12,
  n: 5,
  onNChange: vi.fn(),
  onPickDiverse: vi.fn(),
  picking: false,
  pickCount: 0,
  onAddPicks: vi.fn(),
  onAddAll: vi.fn(),
  onRemove: vi.fn(),
  onClear: vi.fn(),
};

describe("RegionActionBar", () => {
  it("shows the region count", () => {
    render(<RegionActionBar {...baseProps} />);
    expect(screen.getByText(/12 in region/i)).toBeInTheDocument();
  });

  it("Add picks is disabled until there are picks", () => {
    render(<RegionActionBar {...baseProps} pickCount={0} />);
    expect(screen.getByRole("button", { name: /add picks/i })).toBeDisabled();
  });

  it("Add picks enables and reports the pick count", () => {
    render(<RegionActionBar {...baseProps} pickCount={3} />);
    const btn = screen.getByRole("button", { name: /add picks \(3\)/i });
    expect(btn).not.toBeDisabled();
    fireEvent.click(btn);
    expect(baseProps.onAddPicks).toHaveBeenCalled();
  });

  it("Add all reports the region count and fires", () => {
    render(<RegionActionBar {...baseProps} />);
    fireEvent.click(screen.getByRole("button", { name: /add all \(12\)/i }));
    expect(baseProps.onAddAll).toHaveBeenCalled();
  });

  it("Pick diverse fires and is disabled while picking", () => {
    const { rerender } = render(<RegionActionBar {...baseProps} />);
    fireEvent.click(screen.getByRole("button", { name: /pick diverse/i }));
    expect(baseProps.onPickDiverse).toHaveBeenCalled();
    rerender(<RegionActionBar {...baseProps} picking />);
    expect(screen.getByRole("button", { name: /picking/i })).toBeDisabled();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && pnpm vitest run src/features/sar-analysis/components/region-action-bar.test.tsx`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement the component**

Create `src/features/sar-analysis/components/region-action-bar.tsx`:

```typescript
"use client";

import { Button } from "@/shared/components/ui/button";
import { Input } from "@/shared/components/ui/input";
import { Label } from "@/shared/components/ui/label";

interface RegionActionBarProps {
  regionCount: number;
  n: number;
  onNChange: (n: number) => void;
  onPickDiverse: () => void;
  picking: boolean;
  pickCount: number;
  onAddPicks: () => void;
  onAddAll: () => void;
  onRemove: () => void;
  onClear: () => void;
}

export function RegionActionBar(props: RegionActionBarProps) {
  return (
    <div className="flex flex-wrap items-center gap-2 text-xs">
      <span className="font-medium text-foreground">
        {props.regionCount} in region
      </span>
      <span className="text-border">·</span>

      <Label htmlFor="region-n" className="text-muted-foreground">
        N
      </Label>
      <Input
        id="region-n"
        type="number"
        min={1}
        max={1000}
        value={props.n}
        onChange={(e) => props.onNChange(Number(e.target.value))}
        className="h-7 w-16"
      />
      <Button
        size="sm"
        variant="outline"
        onClick={props.onPickDiverse}
        disabled={props.picking || props.regionCount === 0}
      >
        {props.picking ? "Picking…" : "Pick diverse"}
      </Button>

      <Button
        size="sm"
        onClick={props.onAddPicks}
        disabled={props.pickCount === 0}
      >
        Add picks ({props.pickCount})
      </Button>
      <Button size="sm" variant="outline" onClick={props.onAddAll}>
        Add all ({props.regionCount})
      </Button>
      <Button size="sm" variant="outline" onClick={props.onRemove}>
        Remove
      </Button>
      <Button
        size="sm"
        variant="ghost"
        onClick={props.onClear}
        className="text-muted-foreground"
      >
        Clear
      </Button>
    </div>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && pnpm vitest run src/features/sar-analysis/components/region-action-bar.test.tsx`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/features/sar-analysis/components/region-action-bar.tsx \
        frontend/src/features/sar-analysis/components/region-action-bar.test.tsx
git commit -m "feat(sar_analysis): RegionActionBar — lasso region actions (pick/add/remove)"
```

---

### Task 5: `ClusterBasketBar` — basket count + plate hint + Save / Clear / seed-from-picks

**Files:**
- Create: `src/features/sar-analysis/components/cluster-basket-bar.tsx`
- Test: `src/features/sar-analysis/components/cluster-basket-bar.test.tsx`

- [ ] **Step 1: Write the failing test**

Create `src/features/sar-analysis/components/cluster-basket-bar.test.tsx`:

```typescript
import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { ClusterBasketBar } from "./cluster-basket-bar";

const baseProps = {
  count: 0,
  plateTarget: 96,
  repCount: 5,
  onAddRepPicks: vi.fn(),
  onSave: vi.fn(),
  onClear: vi.fn(),
};

describe("ClusterBasketBar", () => {
  it("shows the basket count", () => {
    render(<ClusterBasketBar {...baseProps} count={7} />);
    expect(screen.getByText(/basket: 7/i)).toBeInTheDocument();
  });

  it("shows the plate-target hint only when non-empty", () => {
    const { rerender } = render(<ClusterBasketBar {...baseProps} count={0} />);
    expect(screen.queryByText(/\/ 96/)).not.toBeInTheDocument();
    rerender(<ClusterBasketBar {...baseProps} count={48} />);
    expect(screen.getByText(/48 \/ 96/)).toBeInTheDocument();
  });

  it("Save is disabled when the basket is empty", () => {
    render(<ClusterBasketBar {...baseProps} count={0} />);
    expect(
      screen.getByRole("button", { name: /save as collection/i }),
    ).toBeDisabled();
  });

  it("Save fires when there are compounds", () => {
    render(<ClusterBasketBar {...baseProps} count={3} />);
    fireEvent.click(
      screen.getByRole("button", { name: /save as collection/i }),
    );
    expect(baseProps.onSave).toHaveBeenCalled();
  });

  it("Add Diversify picks reports the rep count and fires", () => {
    render(<ClusterBasketBar {...baseProps} repCount={5} />);
    fireEvent.click(screen.getByRole("button", { name: /add diversify picks \(5\)/i }));
    expect(baseProps.onAddRepPicks).toHaveBeenCalled();
  });

  it("Clear is disabled when empty and fires when not", () => {
    const { rerender } = render(<ClusterBasketBar {...baseProps} count={0} />);
    expect(screen.getByRole("button", { name: /clear basket/i })).toBeDisabled();
    rerender(<ClusterBasketBar {...baseProps} count={2} />);
    fireEvent.click(screen.getByRole("button", { name: /clear basket/i }));
    expect(baseProps.onClear).toHaveBeenCalled();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && pnpm vitest run src/features/sar-analysis/components/cluster-basket-bar.test.tsx`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement the component**

Create `src/features/sar-analysis/components/cluster-basket-bar.tsx`:

```typescript
"use client";

import { Button } from "@/shared/components/ui/button";

interface ClusterBasketBarProps {
  count: number;
  /** Display-only well-plate target for the running-count hint (e.g. 96). */
  plateTarget?: number;
  /** Number of current global Diversify representatives available to seed. */
  repCount: number;
  onAddRepPicks: () => void;
  onSave: () => void;
  onClear: () => void;
}

export function ClusterBasketBar({
  count,
  plateTarget = 96,
  repCount,
  onAddRepPicks,
  onSave,
  onClear,
}: ClusterBasketBarProps) {
  return (
    <div className="flex flex-wrap items-center gap-2 border-b bg-muted/20 px-3 py-1.5 text-xs">
      <span className="font-medium text-foreground">Basket: {count}</span>
      {count > 0 && (
        <span className="text-muted-foreground">
          · {count} / {plateTarget} plate
        </span>
      )}
      <span className="ml-auto flex items-center gap-2">
        <Button
          size="sm"
          variant="outline"
          onClick={onAddRepPicks}
          disabled={repCount === 0}
        >
          Add Diversify picks ({repCount})
        </Button>
        <Button size="sm" onClick={onSave} disabled={count === 0}>
          Save as collection
        </Button>
        <Button
          size="sm"
          variant="ghost"
          onClick={onClear}
          disabled={count === 0}
          className="text-muted-foreground"
        >
          Clear basket
        </Button>
      </span>
    </div>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && pnpm vitest run src/features/sar-analysis/components/cluster-basket-bar.test.tsx`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/features/sar-analysis/components/cluster-basket-bar.tsx \
        frontend/src/features/sar-analysis/components/cluster-basket-bar.test.tsx
git commit -m "feat(sar_analysis): ClusterBasketBar — basket count, plate hint, save/clear"
```

---

### Task 6: Basket + candidate map markers

A pure builder for the two overlay traces, wired into `cluster-scatter.tsx`.

**Files:**
- Create: `src/features/sar-analysis/lib/cluster-overlay.ts`
- Test: `src/features/sar-analysis/lib/cluster-overlay.test.ts`
- Modify: `src/features/sar-analysis/components/cluster-scatter.tsx`

- [ ] **Step 1: Write the failing test**

Create `src/features/sar-analysis/lib/cluster-overlay.test.ts`:

```typescript
import { describe, it, expect } from "vitest";
import { buildOverlayTraces } from "./cluster-overlay";

const points = [
  { moleculeId: "a", x: 0, y: 0 },
  { moleculeId: "b", x: 1, y: 1 },
  { moleculeId: "c", x: 2, y: 2 },
];

describe("buildOverlayTraces", () => {
  it("returns no traces when both sets are empty", () => {
    expect(buildOverlayTraces(points, new Set(), new Set(), "scatter")).toEqual(
      [],
    );
  });

  it("emits a basket trace at the basket members' coordinates", () => {
    const traces = buildOverlayTraces(
      points,
      new Set(["a", "c"]),
      new Set(),
      "scatter",
    );
    expect(traces).toHaveLength(1);
    expect(traces[0].x).toEqual([0, 2]);
    expect(traces[0].y).toEqual([0, 2]);
  });

  it("emits a region-candidate trace when regionPickIds set", () => {
    const traces = buildOverlayTraces(
      points,
      new Set(),
      new Set(["b"]),
      "scatter",
    );
    expect(traces).toHaveLength(1);
    expect(traces[0].x).toEqual([1]);
  });

  it("emits both traces (basket first, then candidates)", () => {
    const traces = buildOverlayTraces(
      points,
      new Set(["a"]),
      new Set(["b"]),
      "scattergl",
    );
    expect(traces).toHaveLength(2);
    expect((traces[0].type as string)).toBe("scattergl");
    expect((traces[1].type as string)).toBe("scattergl");
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && pnpm vitest run src/features/sar-analysis/lib/cluster-overlay.test.ts`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement the builder**

Create `src/features/sar-analysis/lib/cluster-overlay.ts`:

```typescript
interface OverlayPoint {
  moleculeId: string;
  x: number;
  y: number;
}

/**
 * Build the overlay traces drawn ON TOP of the base + star traces:
 *   - in-basket members → emerald open ring ("in your cart")
 *   - region-pick candidates → violet open star ("picked from this region, not yet added")
 *
 * Returns 0–2 traces (basket first so candidates render above it). Pure — unit
 * tested without Plotly.
 */
export function buildOverlayTraces(
  points: OverlayPoint[],
  basketIds: Set<string> | undefined,
  regionPickIds: Set<string> | undefined,
  traceType: string,
): Record<string, unknown>[] {
  const traces: Record<string, unknown>[] = [];

  if (basketIds && basketIds.size > 0) {
    const members = points.filter((p) => basketIds.has(p.moleculeId));
    if (members.length > 0) {
      traces.push({
        type: traceType,
        mode: "markers",
        x: members.map((p) => p.x),
        y: members.map((p) => p.y),
        marker: {
          symbol: "circle-open",
          size: 14,
          line: { width: 2, color: "#059669" },
        },
        hoverinfo: "skip",
      });
    }
  }

  if (regionPickIds && regionPickIds.size > 0) {
    const members = points.filter((p) => regionPickIds.has(p.moleculeId));
    if (members.length > 0) {
      traces.push({
        type: traceType,
        mode: "markers",
        x: members.map((p) => p.x),
        y: members.map((p) => p.y),
        marker: {
          symbol: "star-open",
          size: 16,
          line: { width: 1.5, color: "#7c3aed" },
        },
        hoverinfo: "skip",
      });
    }
  }

  return traces;
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && pnpm vitest run src/features/sar-analysis/lib/cluster-overlay.test.ts`
Expected: PASS.

- [ ] **Step 5: Wire into `cluster-scatter.tsx`**

In `src/features/sar-analysis/components/cluster-scatter.tsx`:

(a) Add the import:

```typescript
import { buildOverlayTraces } from "@/features/sar-analysis/lib/cluster-overlay";
```

(b) Add two props to `ClusterScatterProps` (after `lassoedIds`):

```typescript
  /** Molecule ids currently in the cherry-pick basket — drawn as emerald rings. */
  basketIds?: Set<string>;
  /** Region diverse-pick candidates — drawn as violet open stars. */
  regionPickIds?: Set<string>;
```

(c) Destructure them in the function signature (alongside `lassoedIds`):

```typescript
  lassoedIds,
  basketIds,
  regionPickIds,
```

(d) Replace the `data` assembly line (currently `const data = starTrace ? [baseTrace, starTrace] : [baseTrace];`) with:

```typescript
  const overlayTraces = buildOverlayTraces(
    points,
    basketIds,
    regionPickIds,
    traceType,
  );
  const data = [
    baseTrace,
    ...(starTrace ? [starTrace] : []),
    ...overlayTraces,
  ];
```

- [ ] **Step 6: Verify the existing scatter test still passes**

Run: `cd frontend && pnpm vitest run src/features/sar-analysis/components/cluster-scatter.test.tsx`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/features/sar-analysis/lib/cluster-overlay.ts \
        frontend/src/features/sar-analysis/lib/cluster-overlay.test.ts \
        frontend/src/features/sar-analysis/components/cluster-scatter.tsx
git commit -m "feat(sar_analysis): cluster map markers for basket members + region candidates"
```

---

### Task 7: `ClusterSelectionPane` renders the basket

Repurpose the right pane to show the basket: a header with the count + the basket's molecule cards (reusing `CardGrid`), or an empty hint.

**Files:**
- Modify: `src/features/sar-analysis/components/cluster-selection-pane.tsx`
- Test: `src/features/sar-analysis/components/cluster-selection-pane.test.tsx` (create)

- [ ] **Step 1: Write the failing test**

Create `src/features/sar-analysis/components/cluster-selection-pane.test.tsx`:

```typescript
import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn() }),
}));

// CardGrid virtualizes (heavy in jsdom) — stub it to a simple count.
vi.mock("@/features/research-organization/components/results/card-grid", () => ({
  CardGrid: ({ molecules }: any) => (
    <div data-testid="card-grid">cards:{molecules.length}</div>
  ),
}));

import { ClusterSelectionPane } from "./cluster-selection-pane";

const molecules: any[] = [
  { id: "a", name: "A" },
  { id: "b", name: "B" },
  { id: "c", name: "C" },
];

describe("ClusterSelectionPane", () => {
  it("shows an empty hint when the basket is empty", () => {
    render(
      <ClusterSelectionPane allMolecules={molecules} basketIds={new Set()} />,
    );
    expect(screen.getByText(/basket is empty/i)).toBeInTheDocument();
    expect(screen.queryByTestId("card-grid")).not.toBeInTheDocument();
  });

  it("shows the basket count and cards when non-empty", () => {
    render(
      <ClusterSelectionPane
        allMolecules={molecules}
        basketIds={new Set(["a", "c"])}
      />,
    );
    expect(screen.getByText(/basket \(2\)/i)).toBeInTheDocument();
    expect(screen.getByTestId("card-grid")).toHaveTextContent("cards:2");
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && pnpm vitest run src/features/sar-analysis/components/cluster-selection-pane.test.tsx`
Expected: FAIL — `basketIds` prop / "basket is empty" copy not present.

- [ ] **Step 3: Update the component**

Replace `src/features/sar-analysis/components/cluster-selection-pane.tsx` with:

```typescript
"use client";

import { useState, useCallback } from "react";
import { useRouter } from "next/navigation";
import { CardGrid } from "@/features/research-organization/components/results/card-grid";
import type { Molecule } from "@/features/chemical-registration/types";

interface ClusterSelectionPaneProps {
  allMolecules: Molecule[];
  /** The cherry-pick basket — the durable set the chemist is building. */
  basketIds: Set<string>;
}

export function ClusterSelectionPane({
  allMolecules,
  basketIds,
}: ClusterSelectionPaneProps) {
  const router = useRouter();
  const [gridSelectedIds, setGridSelectedIds] = useState<Set<string>>(
    new Set(),
  );

  const handleSelectChange = useCallback(
    (moleculeId: string, selected: boolean) => {
      setGridSelectedIds((prev) => {
        const next = new Set(prev);
        if (selected) next.add(moleculeId);
        else next.delete(moleculeId);
        return next;
      });
    },
    [],
  );

  const handleOpen = useCallback(
    (moleculeId: string) => router.push(`/compounds/${moleculeId}`),
    [router],
  );

  const hasBasket = basketIds.size > 0;
  const filtered = hasBasket
    ? allMolecules.filter((m) => basketIds.has(m.id))
    : [];

  return (
    <div className="flex h-full flex-col">
      <div className="border-b px-4 py-2 text-xs font-medium text-foreground">
        Basket ({basketIds.size})
      </div>
      {!hasBasket ? (
        <p className="px-4 py-2 text-xs text-muted-foreground">
          Your cherry-pick basket is empty. Lasso a region and add diverse picks,
          or seed it from the Diversify representatives.
        </p>
      ) : (
        // min-h-0 lets this flex child shrink so CardGrid gets a DEFINITE
        // height and its virtualizer can window — otherwise it grows to fit
        // every card. See feedback_virtualized_list_definite_height.
        <div className="flex-1 min-h-0 overflow-auto">
          <CardGrid
            molecules={filtered}
            selectedIds={gridSelectedIds}
            onSelectChange={handleSelectChange}
            onOpen={handleOpen}
          />
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && pnpm vitest run src/features/sar-analysis/components/cluster-selection-pane.test.tsx`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/features/sar-analysis/components/cluster-selection-pane.tsx \
        frontend/src/features/sar-analysis/components/cluster-selection-pane.test.tsx
git commit -m "feat(sar_analysis): cluster pane renders the cherry-pick basket"
```

---

### Task 8: Integrate everything in `cluster-map-view.tsx`

Wire the basket + region hooks, the two bars, and the markers; decouple Diversify from the lasso; drop the toolbar's Save button (moved to the basket bar). Update the affected tests.

**Files:**
- Modify: `src/features/sar-analysis/components/cluster-toolbar.tsx`
- Modify: `src/features/sar-analysis/components/cluster-toolbar.test.tsx`
- Modify: `src/features/sar-analysis/components/cluster-map-view.tsx`
- Modify: `src/features/sar-analysis/components/cluster-map-view.test.tsx`

- [ ] **Step 1: Drop the Save button from `ClusterToolbar`**

In `src/features/sar-analysis/components/cluster-toolbar.tsx`:

(a) Remove `selectedCount` and `onSave` from `ClusterToolbarProps` (delete those two lines).

(b) Delete the entire trailing `<Button ... >Save selection (...)</Button>` block (currently `cluster-toolbar.tsx:95-101`).

- [ ] **Step 2: Update the toolbar test**

In `src/features/sar-analysis/components/cluster-toolbar.test.tsx`, remove any `onSave` / `selectedCount` from the props object passed to `ClusterToolbar`, and delete any test asserting a "Save selection" button. Keep the picker / N / threshold / Diversify tests.

- [ ] **Step 3: Run the toolbar test**

Run: `cd frontend && pnpm vitest run src/features/sar-analysis/components/cluster-toolbar.test.tsx`
Expected: PASS.

- [ ] **Step 4: Update `cluster-map-view.test.tsx` mocks + add basket-flow tests**

Replace the body of `src/features/sar-analysis/components/cluster-map-view.test.tsx` with:

```typescript
import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import React from "react";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), prefetch: vi.fn() }),
  usePathname: () => "/",
  useSearchParams: () => new URLSearchParams(),
}));

vi.mock("@/shared/components/ui/resizable", () => ({
  ResizablePanelGroup: ({ children }: any) => (
    <div data-testid="panel-group">{children}</div>
  ),
  ResizablePanel: ({ children }: any) => <div data-testid="panel">{children}</div>,
  ResizableHandle: () => <div data-testid="resize-handle" />,
}));

vi.mock("@/shared/lib/plotly", () => ({ Plot: () => <div data-testid="plotly" /> }));

// Stub ClusterScatter: clicking it simulates a lasso of {a, b}.
vi.mock("./cluster-scatter", () => ({
  ClusterScatter: ({ onSelected }: any) => (
    <div data-testid="cluster-scatter" onClick={() => onSelected(["a", "b"])} />
  ),
}));

// Basket pane reads `basketIds`.
vi.mock("./cluster-selection-pane", () => ({
  ClusterSelectionPane: ({ basketIds }: any) => (
    <div data-testid="selection-pane">basket:{basketIds.size}</div>
  ),
}));

vi.mock("./save-selection-dialog", () => ({
  SaveSelectionDialog: ({ open, onClose }: any) =>
    open ? (
      <div data-testid="save-dialog">
        <button onClick={onClose}>Close</button>
      </div>
    ) : null,
}));

// Fixed UMAP result (representatives = [a]).
vi.mock("@/features/sar-analysis/hooks/use-umap-cluster", () => ({
  useUmapCluster: vi.fn(() => ({
    result: {
      points: [
        { moleculeId: "a", x: 0, y: 0 },
        { moleculeId: "b", x: 10, y: 10 },
      ],
      clusters: [
        { moleculeId: "a", clusterId: 0 },
        { moleculeId: "b", clusterId: 1 },
      ],
      representatives: [{ moleculeId: "a", clusterId: 0 }],
      clusterCount: 2,
      picker: "maxmin" as const,
      pickerParams: { n: 1 },
      skippedMoleculeIds: [],
    },
    job: null,
    loading: false,
    error: null,
    cancel: vi.fn(),
  })),
}));

// Region pick hook — idle by default.
vi.mock("@/features/sar-analysis/hooks/use-region-diverse-pick", () => ({
  useRegionDiversePick: vi.fn(() => ({
    pickedIds: new Set<string>(),
    loading: false,
    error: null,
    active: false,
    pick: vi.fn(),
    reset: vi.fn(),
  })),
}));

import { ClusterMapView } from "./cluster-map-view";

const molecules: any[] = Array.from({ length: 10 }, (_, i) => ({
  id: String.fromCharCode(97 + i),
  name: `Mol ${i}`,
  bemis_murcko_smiles: "",
  structure: { smiles: "CCC" },
}));

const defaultProps = {
  molecules,
  protocols: [] as any[],
  defaultColorProtocolId: null,
  onSaveCollection: async () => {},
  projects: [],
  defaultProjectId: null,
  sourceLabel: "Test Set",
};

const wrapper = ({ children }: any) => {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
};

describe("ClusterMapView", () => {
  beforeEach(() => window.localStorage.clear());

  it("renders the scatter, basket pane, and split group", () => {
    render(<ClusterMapView {...defaultProps} />, { wrapper });
    expect(screen.getByTestId("cluster-scatter")).toBeInTheDocument();
    expect(screen.getByTestId("selection-pane")).toBeInTheDocument();
    expect(screen.getByTestId("panel-group")).toBeInTheDocument();
    expect(screen.getByTestId("resize-handle")).toBeInTheDocument();
  });

  it("renders the Diversify button and an empty basket bar", () => {
    render(<ClusterMapView {...defaultProps} />, { wrapper });
    expect(
      screen.getByRole("button", { name: /diversify/i }),
    ).toBeInTheDocument();
    expect(screen.getByText(/basket: 0/i)).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /save as collection/i }),
    ).toBeDisabled();
  });

  it("lasso → Add all adds the region to the basket and enables Save", () => {
    render(<ClusterMapView {...defaultProps} />, { wrapper });
    // Simulate a lasso of {a, b}.
    fireEvent.click(screen.getByTestId("cluster-scatter"));
    expect(screen.getByText(/2 in region/i)).toBeInTheDocument();
    // Add all (2) to the basket.
    fireEvent.click(screen.getByRole("button", { name: /add all \(2\)/i }));
    expect(screen.getByText(/basket: 2/i)).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /save as collection/i }),
    ).not.toBeDisabled();
  });

  it("opens the SaveSelectionDialog from the basket bar once non-empty", () => {
    render(<ClusterMapView {...defaultProps} />, { wrapper });
    fireEvent.click(screen.getByTestId("cluster-scatter"));
    fireEvent.click(screen.getByRole("button", { name: /add all \(2\)/i }));
    fireEvent.click(
      screen.getByRole("button", { name: /save as collection/i }),
    );
    expect(screen.getByTestId("save-dialog")).toBeInTheDocument();
  });

  it("Add Diversify picks seeds the basket from representatives", () => {
    render(<ClusterMapView {...defaultProps} />, { wrapper });
    fireEvent.click(
      screen.getByRole("button", { name: /add diversify picks \(1\)/i }),
    );
    expect(screen.getByText(/basket: 1/i)).toBeInTheDocument();
  });

  it("passes collectionId only when on a collection page (XOR moleculeIds)", async () => {
    const { useUmapCluster } = await import(
      "@/features/sar-analysis/hooks/use-umap-cluster"
    );
    (useUmapCluster as any).mockClear();
    render(<ClusterMapView {...defaultProps} collectionId="col-1" />, {
      wrapper,
    });
    const call = (useUmapCluster as any).mock.calls[0][0];
    expect(call.collectionId).toBe("col-1");
    expect(call.moleculeIds).toBeUndefined();
  });

  it("shows a 'not enough molecules' message when fewer than 10 mols", () => {
    render(
      <ClusterMapView {...defaultProps} molecules={molecules.slice(0, 3)} />,
      { wrapper },
    );
    expect(screen.getByText(/need at least 10 molecules/i)).toBeInTheDocument();
    expect(screen.queryByTestId("cluster-scatter")).not.toBeInTheDocument();
  });
});
```

> Note: the map's `useUmapCluster` MUST be called before `useRegionDiversePick` in the component (Step 5) so `mock.calls[0]` remains the map's call for the XOR test.

- [ ] **Step 5: Run the integration test to verify it fails**

Run: `cd frontend && pnpm vitest run src/features/sar-analysis/components/cluster-map-view.test.tsx`
Expected: FAIL — basket bar / region bar / `basketIds` not yet wired.

- [ ] **Step 6: Rewrite `cluster-map-view.tsx`**

Replace `src/features/sar-analysis/components/cluster-map-view.tsx` with:

```typescript
"use client";

import { useCallback, useMemo, useState } from "react";

import {
  ResizableHandle,
  ResizablePanel,
  ResizablePanelGroup,
} from "@/shared/components/ui/resizable";
import type { Molecule } from "@/features/chemical-registration/types";

import { useUmapCluster } from "../hooks/use-umap-cluster";
import { useCherrypickBasket } from "../hooks/use-cherrypick-basket";
import { useRegionDiversePick } from "../hooks/use-region-diverse-pick";
import { usePickerConfig } from "../lib/use-picker-config";
import { useColorMode } from "../lib/use-color-mode";
import type { ColorOption } from "../lib/cluster-palette";
import { ClusterScatter } from "./cluster-scatter";
import { ClusterToolbar } from "./cluster-toolbar";
import { ClusterBasketBar } from "./cluster-basket-bar";
import { RegionActionBar } from "./region-action-bar";
import { ClusterSelectionPane } from "./cluster-selection-pane";
import { ColorModePicker, type ProtocolOption } from "./color-mode-picker";
import { SaveSelectionDialog } from "./save-selection-dialog";

// react-resizable-panels v4: STRING = percent, NUMBER = pixels.
const SCATTER_DEFAULT_PCT = "70%";
const SCATTER_MIN_PCT = "50%";
const SCATTER_MAX_PCT = "80%";
const PANE_DEFAULT_PCT = "30%";
const PANE_MIN_PCT = "20%";
const PANE_MAX_PCT = "50%";

const MIN_MOLS_FOR_UMAP = 10;
const DEFAULT_REGION_N = 12;

export interface ClusterMapViewProps {
  molecules: Molecule[];
  collectionId?: string;
  protocols: ProtocolOption[];
  defaultColorProtocolId: string | null;
  onSaveCollection: (args: {
    name: string;
    projectId: string | null;
    moleculeIds: string[];
  }) => Promise<void>;
  projects: { id: string; name: string }[];
  defaultProjectId: string | null;
  sourceLabel: string;
}

function buildActivityPic50(
  molecules: Molecule[],
  activityData: Record<string, Record<string, any>>,
  protocolId: string | null,
): Record<string, number | null> {
  const out: Record<string, number | null> = {};
  for (const mol of molecules) {
    if (!protocolId) {
      out[mol.id] = null;
      continue;
    }
    const entry = activityData[mol.id]?.[protocolId];
    out[mol.id] = entry?.pic50 ?? entry?.pIC50 ?? null;
  }
  return out;
}

function buildScaffoldByMol(
  molecules: Molecule[],
): Record<string, string | null> {
  const out: Record<string, string | null> = {};
  for (const mol of molecules) {
    const s = (mol as any).bemis_murcko_smiles;
    out[mol.id] = typeof s === "string" && s.length > 0 ? s : null;
  }
  return out;
}

export function ClusterMapView({
  molecules,
  collectionId,
  protocols,
  defaultColorProtocolId,
  onSaveCollection,
  projects,
  defaultProjectId,
  sourceLabel,
}: ClusterMapViewProps) {
  const { picker, n, threshold, setPicker, setN, setThreshold } =
    usePickerConfig({ collectionSize: molecules.length });
  const { mode: colorMode, protocolId: colorProtocolId, setMode: setColorMode } =
    useColorMode({
      defaultMode: defaultColorProtocolId ? "activity" : "cluster",
    });

  // Lasso region (transient).
  const [lassoedIds, setLassoedIds] = useState<Set<string>>(new Set());
  const [regionN, setRegionN] = useState(DEFAULT_REGION_N);
  const [saveOpen, setSaveOpen] = useState(false);

  // Committed picker config — the map only recomputes on Diversify.
  const [committedPicker, setCommittedPicker] = useState(picker);
  const [committedN, setCommittedN] = useState(n);
  const [committedThreshold, setCommittedThreshold] = useState(threshold);
  const isDirty =
    committedPicker !== picker ||
    (picker === "maxmin" && committedN !== n) ||
    committedThreshold !== threshold;

  const allIds = useMemo(() => molecules.map((m) => m.id), [molecules]);

  // --- Map UMAP (must be called BEFORE useRegionDiversePick for the test's
  //     mock.calls[0] ordering). Diversify is decoupled from the lasso: the
  //     map always computes over the whole collection / set.
  const { result, loading, error, cancel } = useUmapCluster({
    collectionId: collectionId ?? undefined,
    moleculeIds: collectionId ? undefined : allIds,
    picker: committedPicker,
    n: committedN,
    threshold: committedThreshold,
    enabled: molecules.length >= MIN_MOLS_FOR_UMAP,
  });

  // --- Cherry-pick basket (persistent) + region diverse-pick (on-demand).
  const basket = useCherrypickBasket(collectionId);
  const region = useRegionDiversePick();

  const repIds: Set<string> = useMemo(
    () => new Set((result?.representatives ?? []).map((r) => r.moleculeId)),
    [result],
  );

  // --- Color derivations.
  const activityPic50 = useMemo(
    () => buildActivityPic50(molecules, {}, colorProtocolId),
    [molecules, colorProtocolId],
  );
  const scaffoldByMol = useMemo(() => buildScaffoldByMol(molecules), [molecules]);

  const labelByMolId = useMemo(() => {
    const map: Record<string, string> = {};
    for (const m of molecules) {
      const reg = (m as { reg_number?: string | null }).reg_number ?? null;
      const name = (m as { name?: string | null }).name ?? null;
      if (reg && name) map[m.id] = `${reg} · ${name}`;
      else if (reg) map[m.id] = reg;
      else if (name) map[m.id] = name;
      else map[m.id] = m.id.slice(0, 8);
    }
    return map;
  }, [molecules]);

  const colorOption: ColorOption = useMemo(() => {
    if (colorMode === "activity" && colorProtocolId)
      return { mode: "activity", protocolId: colorProtocolId };
    if (colorMode === "scaffold") return { mode: "scaffold" };
    if (colorMode === "none") return { mode: "none" };
    return { mode: "cluster" };
  }, [colorMode, colorProtocolId]);

  // --- Handlers.
  const handleLassoSelected = useCallback((ids: string[] | null) => {
    setLassoedIds(new Set(ids ?? []));
  }, []);

  const handlePointClick = useCallback((_moleculeId: string) => {
    // Future: open molecule detail panel.
  }, []);

  const handleDiversify = useCallback(() => {
    setCommittedPicker(picker);
    setCommittedN(n);
    setCommittedThreshold(threshold);
  }, [picker, n, threshold]);

  const handlePickDiverse = useCallback(() => {
    if (lassoedIds.size > 0) region.pick([...lassoedIds], regionN);
  }, [lassoedIds, regionN, region]);

  const handleAddPicks = useCallback(() => {
    basket.addMany([...region.pickedIds]);
    region.reset();
  }, [basket, region]);

  const handleAddAll = useCallback(() => {
    basket.addMany([...lassoedIds]);
  }, [basket, lassoedIds]);

  const handleRemoveRegion = useCallback(() => {
    basket.removeMany([...lassoedIds]);
  }, [basket, lassoedIds]);

  const handleClearRegion = useCallback(() => {
    setLassoedIds(new Set());
    region.reset();
  }, [region]);

  const handleAddRepPicks = useCallback(() => {
    basket.addMany([...repIds]);
  }, [basket, repIds]);

  const handleSave = useCallback(() => {
    if (basket.size > 0) setSaveOpen(true);
  }, [basket.size]);

  const basketMolecules = useMemo(
    () => molecules.filter((m) => basket.ids.has(m.id)),
    [molecules, basket.ids],
  );
  const defaultName = `cherrypick-${basket.size} from ${sourceLabel}`;

  if (molecules.length < MIN_MOLS_FOR_UMAP) {
    return (
      <div className="p-6 text-sm text-muted-foreground">
        Need at least {MIN_MOLS_FOR_UMAP} molecules to compute a cluster map.
        This set has {molecules.length}.
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-6 text-sm text-rose-600">Cluster map failed: {error}</div>
    );
  }

  return (
    <div className="flex flex-col h-[calc(100vh-14rem)] min-h-[480px]">
      <ClusterToolbar
        picker={picker}
        n={n}
        threshold={threshold}
        onPickerChange={setPicker}
        onNChange={setN}
        onThresholdChange={setThreshold}
        onDiversify={handleDiversify}
        diversifyDirty={isDirty}
        colorPicker={
          <ColorModePicker
            mode={colorMode}
            protocolId={colorProtocolId}
            protocols={protocols}
            onChange={setColorMode}
          />
        }
      />

      <ClusterBasketBar
        count={basket.size}
        repCount={repIds.size}
        onAddRepPicks={handleAddRepPicks}
        onSave={handleSave}
        onClear={basket.clear}
      />

      {result && (
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 border-b bg-muted/30 px-3 py-1.5 text-xs text-muted-foreground">
          <span>
            <span className="font-medium text-foreground">
              {result.clusterCount}
            </span>{" "}
            chemotype{result.clusterCount === 1 ? "" : "s"} (Butina @{" "}
            {committedThreshold.toFixed(2)})
          </span>
          <span className="text-border">·</span>
          <span>
            <span className="font-medium text-foreground">
              {result.representatives.length}
            </span>{" "}
            representative{result.representatives.length === 1 ? "" : "s"} (
            {committedPicker === "maxmin"
              ? `MaxMin N=${committedN}`
              : "Butina medoids"}
            )
          </span>
          <span className="text-border">·</span>
          {lassoedIds.size > 0 ? (
            <RegionActionBar
              regionCount={lassoedIds.size}
              n={regionN}
              onNChange={setRegionN}
              onPickDiverse={handlePickDiverse}
              picking={region.loading}
              pickCount={region.pickedIds.size}
              onAddPicks={handleAddPicks}
              onAddAll={handleAddAll}
              onRemove={handleRemoveRegion}
              onClear={handleClearRegion}
            />
          ) : (
            <span>Drag on the map to lasso a region</span>
          )}
        </div>
      )}

      <ResizablePanelGroup
        orientation="horizontal"
        className="flex-1 rounded-md border"
      >
        <ResizablePanel
          defaultSize={SCATTER_DEFAULT_PCT}
          minSize={SCATTER_MIN_PCT}
          maxSize={SCATTER_MAX_PCT}
        >
          <div className="h-full relative">
            {loading && (
              <div className="absolute inset-0 flex items-center justify-center bg-background/60 z-10 text-sm text-muted-foreground">
                <div className="flex flex-col items-center gap-2">
                  <span>Computing cluster map…</span>
                  <button
                    type="button"
                    onClick={cancel}
                    className="text-xs underline text-muted-foreground"
                  >
                    Cancel
                  </button>
                </div>
              </div>
            )}
            {result && (
              <ClusterScatter
                points={result.points}
                clusters={result.clusters}
                representatives={result.representatives}
                colorMode={colorOption}
                activityPic50={activityPic50}
                scaffoldByMol={scaffoldByMol}
                labelByMolId={labelByMolId}
                lassoedIds={lassoedIds}
                basketIds={basket.ids}
                regionPickIds={region.pickedIds}
                onSelected={handleLassoSelected}
                onPointClick={handlePointClick}
              />
            )}
            {!loading && !result && (
              <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
                No cluster data available.
              </div>
            )}
          </div>
        </ResizablePanel>

        <ResizableHandle withHandle />

        <ResizablePanel
          defaultSize={PANE_DEFAULT_PCT}
          minSize={PANE_MIN_PCT}
          maxSize={PANE_MAX_PCT}
        >
          <ClusterSelectionPane
            allMolecules={molecules}
            basketIds={basket.ids}
          />
        </ResizablePanel>
      </ResizablePanelGroup>

      <SaveSelectionDialog
        open={saveOpen}
        onClose={() => setSaveOpen(false)}
        onSave={async (args) => {
          await onSaveCollection(args);
          setSaveOpen(false);
        }}
        selectedMolecules={basketMolecules}
        defaultName={defaultName}
        projects={projects}
        defaultProjectId={defaultProjectId}
      />
    </div>
  );
}
```

- [ ] **Step 7: Run the integration test to verify it passes**

Run: `cd frontend && pnpm vitest run src/features/sar-analysis/components/cluster-map-view.test.tsx`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/features/sar-analysis/components/cluster-toolbar.tsx \
        frontend/src/features/sar-analysis/components/cluster-toolbar.test.tsx \
        frontend/src/features/sar-analysis/components/cluster-map-view.tsx \
        frontend/src/features/sar-analysis/components/cluster-map-view.test.tsx
git commit -m "feat(sar_analysis): cluster lasso → cherry-pick basket (region pick, accumulate, save)"
```

---

### Task 9: Full suite + typecheck + lint

**Files:** none (verification only).

- [ ] **Step 1: Run the sar-analysis suite**

Run: `cd frontend && pnpm vitest run src/features/sar-analysis`
Expected: PASS (all files, including the new hooks/components/lib).

- [ ] **Step 2: Run the whole frontend test suite**

Run: `cd frontend && pnpm vitest run`
Expected: PASS. Investigate any failure outside `sar-analysis` — there should be none (only `cluster-selection-pane` consumers changed, and `ResultsSurface` passes `onSaveCollection` which is unchanged).

- [ ] **Step 3: Typecheck**

Run: `cd frontend && pnpm exec tsc --noEmit`
Expected: clean. Common fix: any leftover `selectedIds` / `onSave` / `selectedCount` references on `ClusterToolbar` or `ClusterSelectionPane` callers.

- [ ] **Step 4: Lint**

Run: `cd frontend && pnpm lint`
Expected: clean (or only pre-existing warnings).

- [ ] **Step 5: Commit any fixups**

```bash
git add -A
git commit -m "chore(sar_analysis): typecheck + lint fixups for cherry-pick basket"
```

(Skip if Steps 1–4 were already clean.)

---

## Browser smoke checklist (run before push)

| # | Scenario | Expected |
|---|----------|----------|
| 1 | Open `chembridge_top5000_kb` → `?view=clusters` | Map renders; basket bar reads `Basket: 0`; Save as collection disabled |
| 2 | Drag a lasso around a blob | Status row switches to `{X} in region` with the region action bar; lassoed points stay opaque, rest dim |
| 3 | Click `Add all ({X})` | Basket bar climbs to `{X}`; those points gain emerald rings; right pane lists them; Save enabled |
| 4 | Lasso a dense blob → set N → `Pick diverse` | Violet open stars appear on N points in the region; `Add picks (N)` enables |
| 5 | `Add picks (N)` | The N candidates become emerald rings; basket count rises by ≤N (de-duped); stars clear |
| 6 | Lasso an overlapping region → `Add all` | Basket rises only by the NEW ids (overlap de-duped) |
| 7 | Lasso a region already basketed → `Remove` | Those rings disappear; basket count drops |
| 8 | `Add Diversify picks (M)` | Basket seeds from the M global representatives |
| 9 | Reload the page | Basket count + rings persist (localStorage) |
| 10 | `Save as collection` → name → Save | New collection created with the basket members; navigates to it |
| 11 | Open a DIFFERENT collection's cluster view | Basket is empty (per-collection key) |
| 12 | Open a >5000-point set (if available) and lasso | Selection still works (polygon path is scattergl-safe) |

---

## Notes for the implementer

- **The lasso fix (Task 1) is the linchpin** — verify smoke #2 actually selects before trusting the rest. The polygon path depends on Plotly emitting `ev.lassoPoints` (data space) on `plotly_selected`; if a Plotly version emits a different shape, log the raw event and extend `selectedIdsFromPlotlyEvent` accordingly (don't fall back to silently forcing SVG).
- **Hook call order in `cluster-map-view.tsx`**: the map's `useUmapCluster` must precede `useRegionDiversePick` so the XOR test inspecting `mock.calls[0]` stays valid.
- **Per-card basket removal** in the right pane is deliberately out of scope — removal is via lasso + `Remove`. Add an inline `×` on the basket cards as a follow-up if chemists ask.
- **Plate target** is display-only (`96`). If chemists want 384 or an active warning on overflow, that's a follow-up — keep V1 honest and non-blocking.
