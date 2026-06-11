import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { UseScaffoldTreeReturn } from "../hooks/use-scaffold-tree";
import type { ScaffoldTreeResult } from "../types/scaffold-tree";

const BENZENE = "c1ccccc1";
const QUINAZOLINE = "c1ccc2ncncc2c1";
const PYRIDINE = "c1ccncc1";

// Mutable hook return, swapped per test via `setTree`.
const h = vi.hoisted(() => ({
  ret: null as unknown as UseScaffoldTreeReturn,
}));

vi.mock("../hooks/use-scaffold-tree", () => ({
  useScaffoldTree: (): UseScaffoldTreeReturn => h.ret,
}));

// RDKit-free shim for the chemistry barrel (StructureThumbnail uses WASM that
// jsdom can't run; StructureEditorDialog pulls in Ketcher).
vi.mock("@/shared/components/chemistry", () => ({
  StructureThumbnail: ({ smiles }: { smiles: string }) => <div data-testid={`thumb-${smiles}`} />,
  StructureEditorDialog: ({
    open,
    onApply,
  }: { open: boolean; onApply: (s: string, f: string) => void }) =>
    open ? (
      <button type="button" data-testid="apply-core" onClick={() => onApply("Nc1ccccc1", "smiles")}>
        apply
      </button>
    ) : null,
}));

import { RGroupCorePicker } from "./rgroup-core-picker";

function setTree(tree: ScaffoldTreeResult | null) {
  h.ret = { tree, jobId: null, isStarting: false, isPolling: false, error: null };
}

/**
 * A congeneric series: 3 quinazolines (a,b,c) + 1 lone pyridine (d). Benzene is
 * the generic ancestor with NO direct members. Coverage: quinazoline 3, benzene
 * 3, pyridine 1. With a floor of 3, pyridine drops and quinazoline (the most
 * specific broadly-shared core) is the default.
 */
const series: ScaffoldTreeResult = {
  nodes: [
    { scaffold_smiles: BENZENE, molecule_ids: [], molecule_count: 0, subtree_molecule_count: 3 },
    {
      scaffold_smiles: QUINAZOLINE,
      molecule_ids: ["a", "b", "c"],
      molecule_count: 3,
      subtree_molecule_count: 3,
    },
    {
      scaffold_smiles: PYRIDINE,
      molecule_ids: ["d"],
      molecule_count: 1,
      subtree_molecule_count: 1,
    },
  ],
  edges: [{ parent_smiles: BENZENE, child_smiles: QUINAZOLINE }],
  stats: { node_count: 3, elapsed_ms: 1, cache_hit: false },
};

/** A diverse set: three unrelated singletons. Nothing clears the floor. */
const diverse: ScaffoldTreeResult = {
  nodes: [
    { scaffold_smiles: BENZENE, molecule_ids: ["a"], molecule_count: 1, subtree_molecule_count: 1 },
    {
      scaffold_smiles: "c1ccoc1",
      molecule_ids: ["b"],
      molecule_count: 1,
      subtree_molecule_count: 1,
    },
    {
      scaffold_smiles: PYRIDINE,
      molecule_ids: ["c"],
      molecule_count: 1,
      subtree_molecule_count: 1,
    },
  ],
  edges: [],
  stats: { node_count: 3, elapsed_ms: 1, cache_hit: false },
};

describe("RGroupCorePicker", () => {
  beforeEach(() => setTree(series));

  it("auto-suggests the most specific broadly-shared core, not the generic ancestor or a singleton", () => {
    const onCoreChange = vi.fn();
    render(
      <RGroupCorePicker
        moleculeIds={["a", "b", "c", "d"]}
        coreSmiles={null}
        onCoreChange={onCoreChange}
      />,
    );
    // quinazoline covers all 3 ring compounds AND is more specific than benzene.
    expect(onCoreChange).toHaveBeenCalledWith(QUINAZOLINE);
    expect(onCoreChange).not.toHaveBeenCalledWith(PYRIDINE);
  });

  it("filters out singleton cores but surfaces 0-direct-member frameworks by coverage", () => {
    render(
      <RGroupCorePicker
        moleculeIds={["a", "b", "c", "d"]}
        coreSmiles={QUINAZOLINE}
        onCoreChange={vi.fn()}
      />,
    );
    // pyridine (coverage 1) is gone; benzene (molecule_count 0, coverage 3) stays.
    expect(screen.queryByTestId(`thumb-${PYRIDINE}`)).toBeNull();
    expect(screen.getByTestId(`thumb-${BENZENE}`)).toBeInTheDocument();
    expect(screen.getByTestId(`thumb-${QUINAZOLINE}`)).toBeInTheDocument();
  });

  it("shows a coverage badge (covers / total) on each candidate", () => {
    render(
      <RGroupCorePicker
        moleculeIds={["a", "b", "c", "d"]}
        coreSmiles={QUINAZOLINE}
        onCoreChange={vi.fn()}
      />,
    );
    // both candidates cover 3 of the 4 loaded compounds
    expect(screen.getAllByText("3/4").length).toBeGreaterThanOrEqual(2);
  });

  it("emits the clicked candidate's core", () => {
    const onCoreChange = vi.fn();
    render(
      <RGroupCorePicker
        moleculeIds={["a", "b", "c", "d"]}
        coreSmiles={QUINAZOLINE}
        onCoreChange={onCoreChange}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: new RegExp(`Select core ${BENZENE}`) }));
    expect(onCoreChange).toHaveBeenCalledWith(BENZENE);
  });

  it("guides instead of auto-suggesting when no scaffold is shared (diverse set)", () => {
    setTree(diverse);
    const onCoreChange = vi.fn();
    render(
      <RGroupCorePicker
        moleculeIds={["a", "b", "c"]}
        coreSmiles={null}
        onCoreChange={onCoreChange}
      />,
    );
    // no auto-suggest, a plain-language guidance panel, and the draw-core CTA
    expect(onCoreChange).not.toHaveBeenCalled();
    expect(screen.getByText(/No shared scaffold/i)).toBeInTheDocument();
    expect(screen.getByText(/covers only 1 of 3/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Draw core/i })).toBeInTheDocument();
  });

  it("shows the matched/unmatched advisory line when counts are provided", () => {
    render(
      <RGroupCorePicker
        moleculeIds={["a", "b", "c", "d"]}
        coreSmiles={QUINAZOLINE}
        onCoreChange={vi.fn()}
        matchedCount={3}
        totalCount={4}
      />,
    );
    expect(screen.getByText(/3 of 4 loaded compounds match this core/)).toBeInTheDocument();
    expect(screen.getByText(/not dropped/)).toBeInTheDocument();
  });

  it("opens the editor and emits the drawn core via onApply", () => {
    const onCoreChange = vi.fn();
    render(
      <RGroupCorePicker moleculeIds={["a"]} coreSmiles={QUINAZOLINE} onCoreChange={onCoreChange} />,
    );
    fireEvent.click(screen.getByText(/Edit core/i));
    fireEvent.click(screen.getByTestId("apply-core"));
    expect(onCoreChange).toHaveBeenCalledWith("Nc1ccccc1");
  });
});
