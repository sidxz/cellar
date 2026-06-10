# SAR Workbench — Frontend Plan A (Foundation: view-mode + R-group table) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `sar` view-mode that, opened on a compound set, lets a chemist pick a core (auto-suggested from the scaffold tree) and see the R-group decomposition as a sortable table (structure + R1…Rn + physchem), with select→save-as-collection. Plus an "Open in SAR" entry from a scaffold-tree node.

**Architecture:** A new `sar` value in the existing `ViewMode` union, rendered as a branch in `results-surface.tsx` (the only host is `collection-detail.tsx`). A new `features/sar-analysis` SAR view component owns: a core picker (reusing the existing `useScaffoldTree` hook to enumerate candidate cores), a hand-written `useRGroupDecomposition` hook (customInstance POST to the Task-4 backend endpoint), and an R-group table built on the shared `DataGrid` + `structureColumn` + `StructureThumbnail`. Activity coloring and the heatmap are **Plan B** — this plan ships the structural table only.

**Tech Stack:** Next.js 16 / React 19 / TS / TanStack Query v5 / AG Grid (via shared `DataGrid`) / RDKit.js (via `StructureThumbnail`/`StructureRenderer`) / Ketcher (via `structure-editor-dialog`) / orval-generated types / vitest.

**Spec:** `docs/superpowers/specs/2026-06-09-sar-workbench-rgroup-design.md` (Phase 1). **Backend:** `POST /api/v1/sar/r-group-decomposition` is live; orval types are generated (commit `394a107c`).

**Scope refinement (verified against the live codebase):**
- The view-mode toggle + `ResultsSurface` are hosted ONLY by `collection-detail.tsx`. The search page (`search-page.tsx`) renders `ResultsGrid` directly with no toggle. **Therefore Phase-1 FE entry = collection detail (view-mode) + scaffold-tree node ("Open in SAR").** Search-results SAR entry is deferred (would require migrating search onto `ResultsSurface`; noted in backlog at end).
- The SAR view fetches its own data (decomposition now; activity in Plan B) — it does NOT rely on `ResultsSurface` threading `activityData`.

**Verified reuse APIs (do not reinvent):**
- `ViewMode` + URL maps: `frontend/src/features/research-organization/lib/use-view-mode.ts` (union + `_ALL_MODES` + `URL_TO_MODE` + `MODE_TO_URL`). Toggle: `components/results/view-mode-toggle.tsx` (one `<Button>` segment per mode).
- `useScaffoldTree({ collectionId | moleculeIds })` → `{ tree, isStarting, isPolling, error }`, `tree.nodes: ScaffoldTreeNode[]` each `{ scaffold_smiles, molecule_ids, molecule_count, subtree_molecule_count }` (`features/sar-analysis/hooks/use-scaffold-tree.ts`, types in `features/sar-analysis/types/scaffold-tree.ts`).
- Generated types (import, do not redefine): `RGroupDecompositionResponse`, `RGroupAssignmentView`, `RGroupDecompositionRequest` from `@/shared/lib/api/model`.
- Request layer: `import { API_V1, customInstance } from "@/shared/lib/api/custom-instance"`.
- Structure render: `import { StructureThumbnail } from "@/shared/components/chemistry"` (square, `size` px); `structureColumn<TRow>(getSmiles)` factory at `features/screening-assay/components/grid-columns.tsx`.
- Grid: shared `DataGrid<TData>` at `shared/components/data-grid/data-grid.tsx` (`rowData`, `columnDefs`, `onRowClick`, `enableMultiSelect`, `suppressSelectColumn`, `onSelectionChanged`, `clearSelectionToken`, `height`).
- Save selection: `SaveSelectionDialog` at `features/sar-analysis/components/save-selection-dialog.tsx` (props: `open,onOpenChange,onSave({name,projectId,moleculeIds}),selectedMolecules,defaultName,projects,defaultProjectId`). Collection create + bulk-add pattern: see `results-surface.tsx::handleSaveClusterCollection`.
- Ketcher core edit: `features/chemical-registration`/`shared/components/chemistry/structure-editor-dialog.tsx` (returns SMILES/SMARTS).
- Scaffold-node action template: `features/sar-analysis/components/scaffold-tree-node.tsx::handleOpenInSearch` → `stashScaffoldSearch` (from `features/research-organization/lib/scaffold-search-handoff`) → `router.push("/search")`.
- Tests: `cd frontend && pnpm test` (vitest run); single file `pnpm test -- <path>`. Lint/format gate: `pnpm lint` (biome — verify by EXIT CODE, never piped output). Playwright E2E is NOT wired up (no runnable command) — do not add E2E tasks.

---

## Task A1: Add the `sar` view-mode

**Files:**
- Modify: `frontend/src/features/research-organization/lib/use-view-mode.ts`
- Modify: `frontend/src/features/research-organization/components/results/view-mode-toggle.tsx`
- Test: `frontend/src/features/research-organization/lib/use-view-mode.test.ts` (create if absent) and the existing `components/results/view-mode-toggle.test.tsx`

- [ ] **Step 1: Write the failing test**

Create/extend `frontend/src/features/research-organization/lib/use-view-mode.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { URL_TO_MODE_TEST as URL_TO_MODE, MODE_TO_URL_TEST as MODE_TO_URL } from "./use-view-mode";

describe("sar view mode mapping", () => {
  it("maps the sar url token both ways", () => {
    expect(URL_TO_MODE.sar).toBe("sar");
    expect(MODE_TO_URL.sar).toBe("sar");
  });
});
```

(If the maps aren't exported, export thin test aliases — see Step 3. If you prefer not to add test-only exports, instead add an assertion in the existing `view-mode-toggle.test.tsx` that renders `<ViewModeToggle mode="sar" ... />` and finds the SAR button; either approach is acceptable, but there MUST be a failing test first.)

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && pnpm test -- src/features/research-organization/lib/use-view-mode.test.ts`
Expected: FAIL (`sar` not in the maps / export missing).

- [ ] **Step 3: Add `sar` to the view-mode**

In `frontend/src/features/research-organization/lib/use-view-mode.ts` make these exact edits:

```ts
export type ViewMode = "table" | "cards" | "scaffold-tree" | "clusters" | "sar";

const _ALL_MODES: ViewMode[] = ["table", "cards", "scaffold-tree", "clusters", "sar"];

const URL_TO_MODE: Record<string, ViewMode> = {
  table: "table",
  cards: "cards",
  tree: "scaffold-tree",
  clusters: "clusters",
  sar: "sar",
};

const MODE_TO_URL: Record<ViewMode, string> = {
  table: "table",
  cards: "cards",
  "scaffold-tree": "tree",
  clusters: "clusters",
  sar: "sar",
};

// Test-only re-exports (used by use-view-mode.test.ts)
export const URL_TO_MODE_TEST = URL_TO_MODE;
export const MODE_TO_URL_TEST = MODE_TO_URL;
```

- [ ] **Step 4: Add the toggle segment**

In `frontend/src/features/research-organization/components/results/view-mode-toggle.tsx`, add `Grid3x3` (or `LayoutDashboard`) to the `lucide-react` import and add a fifth `<Button>` segment after the Cluster one, mirroring the existing segment shape exactly:

```tsx
      <Button
        type="button"
        variant={mode === "sar" ? "default" : "ghost"}
        size="sm"
        className="h-7 px-2 gap-1.5"
        aria-label="SAR view"
        aria-pressed={mode === "sar"}
        disabled={isDisabled("sar")}
        title={isDisabled("sar") ? "Need a few compounds to analyse SAR" : undefined}
        onClick={() => mode !== "sar" && onChange("sar")}
      >
        <Grid3x3 className="h-3.5 w-3.5" />
        <span className="hidden sm:inline text-xs">SAR</span>
      </Button>
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd frontend && pnpm test -- src/features/research-organization/lib/use-view-mode.test.ts src/features/research-organization/components/results/view-mode-toggle.test.tsx`
Expected: PASS. Then `cd frontend && pnpm lint` (expect exit 0).

- [ ] **Step 6: Commit**

```bash
git commit -m "feat(sar): add 'sar' view-mode to the results toggle" -- frontend/src/features/research-organization/lib/use-view-mode.ts frontend/src/features/research-organization/lib/use-view-mode.test.ts frontend/src/features/research-organization/components/results/view-mode-toggle.tsx
```

---

## Task A2: R-group decomposition hook

**Files:**
- Create: `frontend/src/features/sar-analysis/hooks/use-rgroup-decomposition.ts`
- Test: `frontend/src/features/sar-analysis/hooks/use-rgroup-decomposition.test.ts`

- [ ] **Step 1: Write the failing test**

Create `frontend/src/features/sar-analysis/hooks/use-rgroup-decomposition.test.ts`:

```ts
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { useRGroupDecomposition } from "./use-rgroup-decomposition";

function wrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
}

describe("useRGroupDecomposition", () => {
  it("posts the molecule set + core and returns the decomposition", async () => {
    const decomposeFn = vi.fn().mockResolvedValue({
      core_smiles: "c1ccccc1",
      rgroup_labels: ["R1"],
      assignments: [{ molecule_id: "m1", rgroups: { R1: "F[*:1]" } }],
      unmatched_ids: [],
    });
    const { result } = renderHook(
      () => useRGroupDecomposition({ decomposeFn }),
      { wrapper: wrapper() },
    );
    let res: unknown;
    await act(async () => {
      res = await result.current.mutateAsync({ moleculeIds: ["m1"], coreSmiles: "c1ccccc1" });
    });
    expect(decomposeFn).toHaveBeenCalledWith({ molecule_ids: ["m1"], core_smiles: "c1ccccc1" });
    expect((res as { rgroup_labels: string[] }).rgroup_labels).toEqual(["R1"]);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && pnpm test -- src/features/sar-analysis/hooks/use-rgroup-decomposition.test.ts`
Expected: FAIL (module missing).

- [ ] **Step 3: Implement the hook**

Create `frontend/src/features/sar-analysis/hooks/use-rgroup-decomposition.ts`:

```ts
"use client";

import { API_V1, customInstance } from "@/shared/lib/api/custom-instance";
import type { RGroupDecompositionResponse } from "@/shared/lib/api/model";
import { useMutation } from "@tanstack/react-query";

/** One of moleculeIds OR collectionId must be set (the backend enforces xor). */
export interface RGroupDecomposeArgs {
  moleculeIds?: string[];
  collectionId?: string;
  coreSmiles: string;
}

type DecomposeFn = (body: {
  molecule_ids?: string[];
  collection_id?: string;
  core_smiles: string;
}) => Promise<RGroupDecompositionResponse>;

const defaultDecomposeFn: DecomposeFn = (body) =>
  customInstance<RGroupDecompositionResponse>({
    url: `${API_V1}/sar/r-group-decomposition`,
    method: "POST",
    data: body,
  });

/** Injectable `decomposeFn` for tests; defaults to the live POST. */
export function useRGroupDecomposition(opts?: { decomposeFn?: DecomposeFn }) {
  const decomposeFn = opts?.decomposeFn ?? defaultDecomposeFn;
  return useMutation({
    mutationFn: (args: RGroupDecomposeArgs) =>
      decomposeFn(
        args.collectionId
          ? { collection_id: args.collectionId, core_smiles: args.coreSmiles }
          : { molecule_ids: args.moleculeIds ?? [], core_smiles: args.coreSmiles },
      ),
  });
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && pnpm test -- src/features/sar-analysis/hooks/use-rgroup-decomposition.test.ts`
Expected: PASS. Then `cd frontend && pnpm lint` (exit 0).

- [ ] **Step 5: Commit**

```bash
git commit -m "feat(sar): R-group decomposition data hook" -- frontend/src/features/sar-analysis/hooks/use-rgroup-decomposition.ts frontend/src/features/sar-analysis/hooks/use-rgroup-decomposition.test.ts
```

---

## Task A3: "Open in SAR" handoff + scaffold-node action

**Files:**
- Create: `frontend/src/features/sar-analysis/lib/sar-handoff.ts`
- Test: `frontend/src/features/sar-analysis/lib/sar-handoff.test.ts`
- Modify: `frontend/src/features/sar-analysis/components/scaffold-tree-node.tsx`

- [ ] **Step 1: Write the failing test**

Read `frontend/src/features/research-organization/lib/scaffold-search-handoff.ts` first to mirror its sessionStorage stash/read API. Then create `frontend/src/features/sar-analysis/lib/sar-handoff.test.ts`:

```ts
import { beforeEach, describe, expect, it } from "vitest";
import { readSarHandoff, stashSarHandoff } from "./sar-handoff";

describe("sar handoff", () => {
  beforeEach(() => window.sessionStorage.clear());
  it("round-trips a core + molecule ids", () => {
    stashSarHandoff({ coreSmiles: "c1ccccc1", moleculeIds: ["a", "b"] });
    expect(readSarHandoff()).toEqual({ coreSmiles: "c1ccccc1", moleculeIds: ["a", "b"] });
  });
  it("read clears the stash (one-shot)", () => {
    stashSarHandoff({ coreSmiles: "c1ccccc1", moleculeIds: ["a"] });
    readSarHandoff();
    expect(readSarHandoff()).toBeNull();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && pnpm test -- src/features/sar-analysis/lib/sar-handoff.test.ts` → FAIL (module missing).

- [ ] **Step 3: Implement the handoff**

Create `frontend/src/features/sar-analysis/lib/sar-handoff.ts` (one-shot sessionStorage stash, mirroring `scaffold-search-handoff.ts`):

```ts
const KEY = "cellar:sar-handoff";

export interface SarHandoff {
  coreSmiles: string;
  moleculeIds: string[];
}

export function stashSarHandoff(payload: SarHandoff): void {
  try {
    window.sessionStorage.setItem(KEY, JSON.stringify(payload));
  } catch {
    /* sessionStorage unavailable — ignore */
  }
}

/** Reads and clears the stash (one-shot). Returns null if absent/invalid. */
export function readSarHandoff(): SarHandoff | null {
  try {
    const raw = window.sessionStorage.getItem(KEY);
    if (!raw) return null;
    window.sessionStorage.removeItem(KEY);
    const parsed = JSON.parse(raw) as SarHandoff;
    if (typeof parsed?.coreSmiles !== "string" || !Array.isArray(parsed?.moleculeIds)) return null;
    return parsed;
  } catch {
    return null;
  }
}
```

- [ ] **Step 4: Add the scaffold-node "Open in SAR" button**

In `frontend/src/features/sar-analysis/components/scaffold-tree-node.tsx`: import `stashSarHandoff` from `../lib/sar-handoff` and the `FlaskConical` (or `Grid3x3`) icon from `lucide-react`. Mirror the existing `handleOpenInSearch` to add (next to it):

```tsx
  const handleOpenInSar = (e: React.MouseEvent) => {
    e.stopPropagation();
    if (scaffoldSmiles === NO_SCAFFOLD_SENTINEL) return; // no core to seed
    stashSarHandoff({ coreSmiles: scaffoldSmiles, moleculeIds: node.molecule_ids });
    // Route to the node's collection in SAR view-mode when available; otherwise
    // the SAR view reads the handoff. (collectionId is threaded into the tree;
    // if not available here, route to /search?view=sar as the generic target.)
    router.push(`/collections/${collectionId ?? ""}?view=sar`);
  };
```

Add the button beside the existing search button (clone its markup, swap icon + `aria-label="Analyse SAR for this scaffold"` + `onClick={handleOpenInSar}`). NOTE: `node` is resolved at the existing `const node = nodesBySmiles.get(scaffoldSmiles); if (!node) return null;`. If `collectionId` is not currently a prop on this component, thread it from `scaffold-tree-view.tsx` (which has `collectionId`) the same way `nodesBySmiles` is threaded — OR, if that's more than a trivial thread, route to `/search?view=sar` and rely on `readSarHandoff()` in the SAR view (acceptable for v1; document the choice in the commit).

- [ ] **Step 5: Run tests + lint**

Run: `cd frontend && pnpm test -- src/features/sar-analysis/lib/sar-handoff.test.ts` → PASS. `cd frontend && pnpm lint` → exit 0.

- [ ] **Step 6: Commit**

```bash
git commit -m "feat(sar): one-shot 'Open in SAR' handoff from scaffold tree" -- frontend/src/features/sar-analysis/lib/sar-handoff.ts frontend/src/features/sar-analysis/lib/sar-handoff.test.ts frontend/src/features/sar-analysis/components/scaffold-tree-node.tsx
```

---

## Task A4: Core picker

**Files:**
- Create: `frontend/src/features/sar-analysis/components/rgroup-core-picker.tsx`
- Test: `frontend/src/features/sar-analysis/components/rgroup-core-picker.test.tsx`

**Responsibility:** given the set context (`collectionId` or `moleculeIds`), enumerate candidate cores from the scaffold tree, let the user pick one (default = highest `molecule_count` ringed node), and emit the chosen `coreSmiles`. Offer "Edit/Draw core" via the Ketcher dialog. Show the matched/unmatched split AFTER decomposition (passed in as props from the SAR view, which owns the decomposition mutation).

**Interface:**
```tsx
export interface RGroupCorePickerProps {
  collectionId?: string;
  moleculeIds?: string[];
  /** Currently selected core (controlled by the SAR view). */
  coreSmiles: string | null;
  onCoreChange: (coreSmiles: string) => void;
  /** From the latest decomposition, for the matched/unmatched line. */
  matchedCount?: number;
  totalCount?: number;
}
```

- [ ] **Step 1: Write the failing test** — render with an injected scaffold-tree result (mock `useScaffoldTree`), assert the dominant scaffold is preselected and clicking another candidate calls `onCoreChange` with its SMILES. (Mirror the existing `scaffold-tree-view.test.tsx` mocking approach for `useScaffoldTree`.)

```tsx
import { render, screen, fireEvent } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("../hooks/use-scaffold-tree", () => ({
  useScaffoldTree: () => ({
    tree: {
      nodes: [
        { scaffold_smiles: "c1ccccc1", molecule_ids: ["a", "b", "c"], molecule_count: 3, subtree_molecule_count: 3 },
        { scaffold_smiles: "c1ccncc1", molecule_ids: ["d"], molecule_count: 1, subtree_molecule_count: 1 },
      ],
    },
    isStarting: false, isPolling: false, error: null,
  }),
}));

import { RGroupCorePicker } from "./rgroup-core-picker";

describe("RGroupCorePicker", () => {
  it("preselects the dominant scaffold and emits on change", () => {
    const onCoreChange = vi.fn();
    render(<RGroupCorePicker moleculeIds={["a","b","c","d"]} coreSmiles={null} onCoreChange={onCoreChange} />);
    // auto-suggest fires onCoreChange with the dominant core on mount
    expect(onCoreChange).toHaveBeenCalledWith("c1ccccc1");
    fireEvent.click(screen.getByText(/c1ccncc1/));
    expect(onCoreChange).toHaveBeenCalledWith("c1ccncc1");
  });
});
```

- [ ] **Step 2: Run → FAIL.** `cd frontend && pnpm test -- src/features/sar-analysis/components/rgroup-core-picker.test.tsx`

- [ ] **Step 3: Implement** — key logic (full component follows the styling of `scaffold-groups-list.tsx`):

```tsx
"use client";

import { StructureThumbnail } from "@/shared/components/chemistry";
import { Button } from "@/shared/components/ui/button";
import { useEffect, useMemo, useState } from "react";
import { useScaffoldTree } from "../hooks/use-scaffold-tree";
import { NO_SCAFFOLD_SENTINEL } from "../types/scaffold-tree";
import { StructureEditorDialog } from "@/shared/components/chemistry/structure-editor-dialog";

export interface RGroupCorePickerProps {
  collectionId?: string;
  moleculeIds?: string[];
  coreSmiles: string | null;
  onCoreChange: (coreSmiles: string) => void;
  matchedCount?: number;
  totalCount?: number;
}

export function RGroupCorePicker(props: RGroupCorePickerProps) {
  const { tree, isStarting, isPolling } = useScaffoldTree({
    collectionId: props.collectionId,
    moleculeIds: props.moleculeIds,
  });
  const [editOpen, setEditOpen] = useState(false);

  // Candidate cores = ringed scaffold nodes, ranked by membership (desc).
  const candidates = useMemo(
    () =>
      (tree?.nodes ?? [])
        .filter((n) => n.scaffold_smiles !== NO_SCAFFOLD_SENTINEL)
        .sort((a, b) => b.molecule_count - a.molecule_count),
    [tree],
  );

  // Auto-suggest the dominant core once, when none is selected yet.
  useEffect(() => {
    if (props.coreSmiles == null && candidates.length > 0) {
      props.onCoreChange(candidates[0].scaffold_smiles);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [candidates, props.coreSmiles]);

  if (isStarting || isPolling) return <p className="text-xs text-muted-foreground">Finding scaffolds…</p>;

  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center gap-2 flex-wrap">
        <span className="text-xs uppercase tracking-wide text-muted-foreground">Core</span>
        {candidates.map((n) => (
          <button
            key={n.scaffold_smiles}
            type="button"
            onClick={() => props.onCoreChange(n.scaffold_smiles)}
            className={`flex items-center gap-2 rounded-md border px-2 py-1 text-xs ${
              props.coreSmiles === n.scaffold_smiles ? "border-primary bg-primary/5 font-semibold" : "border-input"
            }`}
          >
            <StructureThumbnail smiles={n.scaffold_smiles} size={44} />
            <span className="font-mono">{n.scaffold_smiles}</span>
            <span className="text-muted-foreground">{n.molecule_count}</span>
          </button>
        ))}
        <Button variant="outline" size="sm" className="h-7" onClick={() => setEditOpen(true)}>
          ✎ Edit / draw core
        </Button>
      </div>
      {props.matchedCount != null && props.totalCount != null && (
        <p className="text-xs text-amber-700">
          {props.matchedCount} of {props.totalCount} match this core
          {props.matchedCount < props.totalCount ? " · others shown separately, not dropped" : ""}
        </p>
      )}
      <StructureEditorDialog
        open={editOpen}
        onOpenChange={setEditOpen}
        initialValue={props.coreSmiles ?? ""}
        onSave={(smiles) => { setEditOpen(false); if (smiles) props.onCoreChange(smiles); }}
      />
    </div>
  );
}
```
NOTE: confirm the actual prop names of `StructureEditorDialog` (open/onOpenChange/initialValue/onSave or similar) by reading the file; adapt the call to its real API. If `useScaffoldTree` requires ≥1 of collectionId/moleculeIds, the SAR view must always pass one.

- [ ] **Step 4: Run → PASS** + `pnpm lint` (exit 0).
- [ ] **Step 5: Commit** `git commit -m "feat(sar): core picker (auto-suggest from scaffold tree + edit)" -- frontend/src/features/sar-analysis/components/rgroup-core-picker.tsx frontend/src/features/sar-analysis/components/rgroup-core-picker.test.tsx`

---

## Task A5: R-group table

**Files:**
- Create: `frontend/src/features/sar-analysis/components/rgroup-table.tsx`
- Test: `frontend/src/features/sar-analysis/components/rgroup-table.test.tsx`

**Responsibility:** given a `RGroupDecompositionResponse` + the molecules (for structure + physchem), render a `DataGrid` with: structure thumbnail, `#`, one column per `rgroup_labels` entry (rendered as the substituent — small `StructureThumbnail` of the R-group SMILES + the SMILES text), and physchem columns (MW, LogP, TPSA from `molecule.descriptors`). Multi-select → `selectionToolbar`/`onSelectionChanged`; the toolbar exposes "Save as collection" (reusing `SaveSelectionDialog`). Activity columns + row→curve are Plan B.

**Interface:**
```tsx
export interface RGroupTableProps {
  decomposition: RGroupDecompositionResponse;
  molecules: Molecule[];              // for smiles + descriptors, joined by molecule_id
  onSaveSelection: (moleculeIds: string[]) => void;  // SAR view wires SaveSelectionDialog
}
```

- [ ] **Step 1: Write the failing test** — build a row model from a 2-assignment decomposition + matching molecules; assert the grid shows an R1 column and the two reg numbers. (Mock `DataGrid` to render `rowData`/`columnDefs` count, mirroring how existing grid component tests stub AG Grid — check an existing `*-columns.test.tsx`/`results-grid` test for the stub pattern; AG Grid is heavy in jsdom so tests assert on the column/row builder output, not full grid render.)

Prefer testing a PURE row/column builder. Extract `buildRGroupRows(decomposition, molecules)` and `buildRGroupColumns(rgroup_labels)` as exported pure functions and unit-test those directly:

```tsx
import { describe, expect, it } from "vitest";
import { buildRGroupRows, buildRGroupColumns } from "./rgroup-table";

const decomp = {
  core_smiles: "c1ccccc1",
  rgroup_labels: ["R1", "R2"],
  assignments: [
    { molecule_id: "m1", rgroups: { R1: "F[*:1]", R2: "[H][*:2]" } },
    { molecule_id: "m2", rgroups: { R1: "Cl[*:1]", R2: "[H][*:2]" } },
  ],
  unmatched_ids: [],
};
const mols = [
  { id: "m1", registration_number: "CV-1", structure: { smiles: "Fc1ccccc1" }, descriptors: { molecular_weight: 96, clogp: 2.1, tpsa: 0 } },
  { id: "m2", registration_number: "CV-2", structure: { smiles: "Clc1ccccc1" }, descriptors: { molecular_weight: 112, clogp: 2.5, tpsa: 0 } },
] as any;

describe("rgroup-table builders", () => {
  it("builds one row per matched assignment with R-group values", () => {
    const rows = buildRGroupRows(decomp as any, mols);
    expect(rows).toHaveLength(2);
    expect(rows[0].rgroups.R1).toBe("F[*:1]");
    expect(rows[0].smiles).toBe("Fc1ccccc1");
    expect(rows[0].registration_number).toBe("CV-1");
  });
  it("builds a column per rgroup label", () => {
    const cols = buildRGroupColumns(["R1", "R2"]);
    expect(cols.map((c) => c.colId)).toEqual(expect.arrayContaining(["rg:R1", "rg:R2"]));
  });
});
```

- [ ] **Step 2: Run → FAIL.**

- [ ] **Step 3: Implement** — the pure builders + the component. Key code:

```tsx
"use client";

import type { Molecule } from "@/features/chemical-registration/types";
import { StructureThumbnail } from "@/shared/components/chemistry";
import { DataGrid } from "@/shared/components/data-grid/data-grid";
import { structureColumn } from "@/features/screening-assay/components/grid-columns";
import type { RGroupDecompositionResponse } from "@/shared/lib/api/model";
import type { ColDef } from "ag-grid-community";

export interface RGroupRow {
  id: string;
  registration_number: string | null;
  name: string | null;
  smiles: string | null;
  rgroups: Record<string, string>;
  mw: number | null;
  clogp: number | null;
  tpsa: number | null;
}

export function buildRGroupRows(d: RGroupDecompositionResponse, molecules: Molecule[]): RGroupRow[] {
  const byId = new Map(molecules.map((m) => [m.id, m]));
  return d.assignments.map((a) => {
    const m = byId.get(a.molecule_id);
    return {
      id: a.molecule_id,
      registration_number: m?.registration_number ?? null,
      name: m?.name ?? null,
      smiles: m?.structure?.smiles ?? null,
      rgroups: a.rgroups,
      mw: m?.descriptors?.molecular_weight ?? null,
      clogp: m?.descriptors?.clogp ?? null,
      tpsa: m?.descriptors?.tpsa ?? null,
    };
  });
}

export function buildRGroupColumns(labels: string[]): ColDef<RGroupRow>[] {
  const cols: ColDef<RGroupRow>[] = [
    structureColumn<RGroupRow>((r) => r.smiles),
  ];
  for (const label of labels) {
    cols.push({
      headerName: label,
      colId: `rg:${label}`,
      width: 110,
      valueGetter: (p) => p.data?.rgroups[label] ?? "",
      cellRenderer: (p: { data?: RGroupRow }) => {
        const smi = p.data?.rgroups[label];
        if (!smi) return <span className="text-muted-foreground">—</span>;
        return (
          <div className="flex items-center gap-1">
            <StructureThumbnail smiles={smi} size={40} />
            <span className="font-mono text-[11px]">{smi}</span>
          </div>
        );
      },
    });
  }
  cols.push(
    { headerName: "MW", colId: "mw", width: 90, valueGetter: (p) => p.data?.mw ?? null },
    { headerName: "cLogP", colId: "clogp", width: 90, valueGetter: (p) => p.data?.clogp ?? null },
    { headerName: "TPSA", colId: "tpsa", width: 90, valueGetter: (p) => p.data?.tpsa ?? null },
  );
  return cols;
}
```
Component body renders `<DataGrid<RGroupRow> rowData={buildRGroupRows(...)} columnDefs={buildRGroupColumns(decomposition.rgroup_labels)} height="70vh" enableMultiSelect suppressSelectColumn onSelectionChanged={...} selectionToolbar={(rows) => <Button onClick={() => onSaveSelection(rows.map(r=>r.id))}>Save as collection</Button>} />`. VERIFY `Molecule.descriptors` field names (`molecular_weight`/`clogp`/`tpsa`) against `features/chemical-registration/types` — adapt if different.

- [ ] **Step 4: Run → PASS** + `pnpm lint`.
- [ ] **Step 5: Commit** `git commit -m "feat(sar): R-group decomposition table" -- frontend/src/features/sar-analysis/components/rgroup-table.tsx frontend/src/features/sar-analysis/components/rgroup-table.test.tsx`

---

## Task A6: SAR view shell + wire into collection detail

**Files:**
- Create: `frontend/src/features/sar-analysis/components/sar-view.tsx`
- Modify: `frontend/src/features/research-organization/components/results/results-surface.tsx`
- Modify: `frontend/src/features/research-organization/components/collection-detail.tsx`
- Test: `frontend/src/features/sar-analysis/components/sar-view.test.tsx`

**Responsibility:** `sar-view.tsx` composes the core picker + the R-group table, owns the `useRGroupDecomposition` mutation (re-runs when the core changes), reads `readSarHandoff()` on mount to seed the core, and wires `SaveSelectionDialog` (create collection + bulk-add, reusing the `handleSaveClusterCollection` pattern — extract that helper to share, or duplicate the 3-step create→add→navigate).

**Interface:**
```tsx
export interface SarViewProps {
  molecules: Molecule[];
  collectionId?: string;
  projects: { id: string; name: string }[];
  defaultProjectId: string | null;
  sourceLabel: string;
}
```

- [ ] **Step 1: Write the failing test** — render `SarView` with injected molecules + a mocked `useRGroupDecomposition` (returns a fixed decomposition) and a mocked `useScaffoldTree`; assert that after a core is auto-picked, the decomposition mutation is called with `{ moleculeIds, coreSmiles }` and the table renders. Keep it light (mock the heavy children).

- [ ] **Step 2: Run → FAIL.**

- [ ] **Step 3: Implement `sar-view.tsx`** — composition + the decompose-on-core-change effect:

```tsx
"use client";

import type { Molecule } from "@/features/chemical-registration/types";
import { useCreateCollection } from "@/features/research-organization/hooks/use-collections";
import { API_V1, customInstance } from "@/shared/lib/api/custom-instance";
import { useEffect, useState } from "react";
import { useRGroupDecomposition } from "../hooks/use-rgroup-decomposition";
import { readSarHandoff } from "../lib/sar-handoff";
import { RGroupCorePicker } from "./rgroup-core-picker";
import { RGroupTable } from "./rgroup-table";
import { SaveSelectionDialog } from "./save-selection-dialog";

export interface SarViewProps {
  molecules: Molecule[];
  collectionId?: string;
  projects: { id: string; name: string }[];
  defaultProjectId: string | null;
  sourceLabel: string;
}

export function SarView(props: SarViewProps) {
  const moleculeIds = props.molecules.map((m) => m.id);
  const decompose = useRGroupDecomposition();
  const createCollection = useCreateCollection();
  const [core, setCore] = useState<string | null>(() => readSarHandoff()?.coreSmiles ?? null);
  const [saveIds, setSaveIds] = useState<string[] | null>(null);

  // Re-run decomposition whenever the chosen core changes.
  useEffect(() => {
    if (!core) return;
    decompose.mutate({ moleculeIds, coreSmiles: core });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [core, props.collectionId]);

  const result = decompose.data;

  return (
    <div className="flex flex-col gap-3">
      <RGroupCorePicker
        collectionId={props.collectionId}
        moleculeIds={moleculeIds}
        coreSmiles={core}
        onCoreChange={setCore}
        matchedCount={result?.assignments.length}
        totalCount={result ? result.assignments.length + result.unmatched_ids.length : undefined}
      />
      {decompose.isPending && <p className="text-xs text-muted-foreground">Decomposing…</p>}
      {result && (
        <RGroupTable decomposition={result} molecules={props.molecules} onSaveSelection={setSaveIds} />
      )}
      {/* SaveSelectionDialog: create collection + bulk-add (reuse the cluster pattern). */}
      <SaveSelectionDialog
        open={saveIds != null}
        onOpenChange={(o) => !o && setSaveIds(null)}
        onSave={async ({ name, projectId, moleculeIds }) => {
          const created = await new Promise<{ id: string }>((resolve, reject) =>
            createCollection.mutate(
              { name, project_id: projectId },
              { onSuccess: (c) => resolve(c as { id: string }), onError: reject },
            ),
          );
          if (moleculeIds.length > 0) {
            await customInstance({
              url: `${API_V1}/collections/${created.id}/molecules`,
              method: "POST",
              data: { references: moleculeIds.map((id) => ({ value: id, ref_type: "uuid" })) },
            });
          }
          setSaveIds(null);
        }}
        selectedMolecules={props.molecules.filter((m) => saveIds?.includes(m.id))}
        defaultName={`SAR selection from ${props.sourceLabel}`}
        projects={props.projects}
        defaultProjectId={props.defaultProjectId}
      />
    </div>
  );
}
```
(The `onSave` mirrors `results-surface.tsx::handleSaveClusterCollection` — create collection, bulk-add by UUID reference, close. It does not navigate away, unlike the cluster version, so the chemist stays in the SAR view.)

- [ ] **Step 4: Wire the branch in `results-surface.tsx`** — add `import { SarView } from "@/features/sar-analysis/components/sar-view"`, and a new branch BEFORE the final `table` fallback:

```tsx
      ) : mode === "sar" ? (
        <SarView
          molecules={molecules}
          collectionId={collectionId}
          projects={clusterProjects ?? []}
          defaultProjectId={clusterDefaultProjectId ?? null}
          sourceLabel={clusterSourceLabel ?? "this set"}
        />
      ) : mode === "cards" ? (
```

(Reuses the cluster props already threaded by `collection-detail.tsx`: `clusterProjects`, `clusterDefaultProjectId`, `clusterSourceLabel`. No new prop threading needed for Plan A.)

- [ ] **Step 5: Confirm collection-detail enables the mode** — `collection-detail.tsx` already renders the toggle via `useViewMode` + `ViewModeToggle`; adding `"sar"` to the union (Task A1) makes the segment appear automatically. If there's a `disabledModes` gate, optionally add a small minimum (e.g. disable SAR under 3 molecules) mirroring the `clusterDisabledModes` pattern. No structural change required.

- [ ] **Step 6: Run tests + lint**

Run: `cd frontend && pnpm test -- src/features/sar-analysis/` (all SAR tests) → PASS. `cd frontend && pnpm lint` → exit 0.

- [ ] **Step 7: Commit**

```bash
git commit -m "feat(sar): SAR view shell + collection-detail view-mode wiring" -- frontend/src/features/sar-analysis/components/sar-view.tsx frontend/src/features/sar-analysis/components/sar-view.test.tsx frontend/src/features/research-organization/components/results/results-surface.tsx
```

---

## Plan A Done — verification

- [ ] `cd frontend && pnpm test -- src/features/sar-analysis/ src/features/research-organization/lib/use-view-mode.test.ts` — green.
- [ ] `cd frontend && pnpm lint` — exit 0 (biome; verify by exit code, not piped output).
- [ ] Manual smoke (backend on :8000, `cd frontend && pnpm dev`): open a collection with a congeneric series → toggle **SAR** → a core is auto-picked → the R-group table renders structure + R1…Rn + physchem → select rows → Save as collection works. And: in the collection's **Scaffold** view, a node's "Open in SAR" routes to the SAR view with that core seeded.
- [ ] Update the GitHub project board (SAR workbench — frontend foundation done).
- [ ] **Next plan (Plan B — activity + heatmap):** add the "Color by" control (protocol→readout→aggregation, reusing `useProtocolSummaries` + `buildActivityWhereOptions` + `AggregationControl` + `drcColId`/`rdColId` + `toBackendProtocolColumns`), fetch activity via `useExecuteSearch` with a `{type:"keyword_list", values: moleculeIds, ref_type:"uuid"}` criterion, color the table cells by `findInterceptValue(av.intercept_values, spec)?.value ?? av.value` with Δ-vs-reference shading, add row→`DoseResponseFigure`, and build the 2-axis heatmap (`rgroup_labels` axes, empty=gaps, +N collapse) as a sub-toggle in `sar-view.tsx`.
- [ ] **Backlog:** SAR view-mode on **search results** is deferred — `search-page.tsx` renders `ResultsGrid` directly (no `ResultsSurface`/toggle). Adding it requires migrating search onto `ResultsSurface` or adding a parallel toggle+branch. Record in `docs/backlog/`.
