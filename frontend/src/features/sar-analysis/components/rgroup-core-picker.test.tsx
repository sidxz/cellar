import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { McsResult, UseMcsReturn } from "../hooks/use-mcs";
import type { UseScaffoldTreeReturn } from "../hooks/use-scaffold-tree";
import type { ScaffoldTreeResult } from "../types/scaffold-tree";

const BENZENE = "c1ccccc1";
const QUINAZOLINE = "c1ccc2ncncc2c1";
const PYRIDINE = "c1ccncc1";

// Mutable hook return, swapped per test via `setTree`.
const h = vi.hoisted(() => ({
  ret: null as unknown as UseScaffoldTreeReturn,
}));

const m = vi.hoisted(() => ({
  ret: { mcs: null, isLoading: false, error: null, outOfRange: false } as UseMcsReturn,
}));

vi.mock("../hooks/use-scaffold-tree", () => ({
  useScaffoldTree: (): UseScaffoldTreeReturn => h.ret,
}));

// The MCS is a separate query; default it to "nothing shared" so the existing
// scaffold cases are unaffected, and set it per test where it matters.
vi.mock("../hooks/use-mcs", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../hooks/use-mcs")>();
  return {
    ...actual,
    useMcs: (): UseMcsReturn => m.ret,
  };
});

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

function setMcs(mcs: Partial<McsResult> | null) {
  m.ret = {
    mcs: mcs
      ? {
          smarts: "[#6]1:[#6]:[#6]:[#6]:[#6]:[#6]:1",
          core_smiles: QUINAZOLINE,
          num_atoms: 10,
          num_bonds: 11,
          timed_out: false,
          molecule_count: 4,
          ...mcs,
        }
      : null,
    isLoading: false,
    error: null,
    outOfRange: false,
  };
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
  beforeEach(() => {
    setTree(series);
    setMcs(null);
  });

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

  it("opens the editor and emits the drawn core via onApply", () => {
    const onCoreChange = vi.fn();
    render(
      <RGroupCorePicker moleculeIds={["a"]} coreSmiles={QUINAZOLINE} onCoreChange={onCoreChange} />,
    );
    fireEvent.click(screen.getByText(/Edit core/i));
    fireEvent.click(screen.getByTestId("apply-core"));
    expect(onCoreChange).toHaveBeenCalledWith("Nc1ccccc1");
  });

  // --- Maximum common substructure ----------------------------------------
  // The MCS is offered, never chosen for the chemist. It is maximal by
  // construction, which makes it the best core for a tight series and a
  // benzene for a loose one, and one stray control compound in a collection
  // collapses it — so a wrong guess has to cost a click, not a wrong table.

  it("offers the shared substructure but never auto-suggests it", () => {
    setMcs({ core_smiles: PYRIDINE, molecule_count: 4 });
    const onCoreChange = vi.fn();
    render(
      <RGroupCorePicker
        moleculeIds={["a", "b", "c", "d"]}
        coreSmiles={null}
        onCoreChange={onCoreChange}
      />,
    );

    expect(screen.getByTestId(`thumb-${PYRIDINE}`)).toBeInTheDocument();
    // The scaffold default still wins the auto-suggest; the MCS waits to be asked.
    expect(onCoreChange).toHaveBeenCalledTimes(1);
    expect(onCoreChange).toHaveBeenCalledWith(QUINAZOLINE);
  });

  it("labels the shared substructure by its guarantee, not by a coverage ratio", () => {
    // A scaffold chip's "3/4" means three compounds contain it — one falls out
    // of the table. The MCS keeps every compound, and says so.
    setMcs({ core_smiles: PYRIDINE, molecule_count: 4 });
    render(
      <RGroupCorePicker
        moleculeIds={["a", "b", "c", "d"]}
        coreSmiles={null}
        onCoreChange={vi.fn()}
      />,
    );

    expect(screen.getByText("all 4")).toBeInTheDocument();
    // The scaffold chips keep their ratio (two of them cover 3 of 4 here).
    expect(screen.getAllByText("3/4").length).toBeGreaterThan(0);
  });

  it("emits the shared substructure when picked", () => {
    setMcs({ core_smiles: PYRIDINE, molecule_count: 4 });
    const onCoreChange = vi.fn();
    render(
      <RGroupCorePicker
        moleculeIds={["a", "b", "c", "d"]}
        coreSmiles={QUINAZOLINE}
        onCoreChange={onCoreChange}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /shared substructure as the core/i }));
    expect(onCoreChange).toHaveBeenCalledWith(PYRIDINE);
  });

  it("withholds a timed-out or empty substructure", () => {
    // A timed-out search returns its best-so-far, which is smaller than the
    // true MCS; decomposing against it overstates how much the series varies.
    setMcs({ core_smiles: PYRIDINE, timed_out: true });
    const { unmount } = render(
      <RGroupCorePicker moleculeIds={["a", "b"]} coreSmiles={null} onCoreChange={vi.fn()} />,
    );
    expect(screen.queryByTestId(`thumb-${PYRIDINE}`)).not.toBeInTheDocument();
    unmount();

    setMcs({ core_smiles: null, num_atoms: 0 });
    render(<RGroupCorePicker moleculeIds={["a", "b"]} coreSmiles={null} onCoreChange={vi.fn()} />);
    expect(screen.queryByText(/all 4/)).not.toBeInTheDocument();
  });

  it("answers the acyclic series the scaffold network cannot see", () => {
    // Candidates come only from ring scaffolds, and an acyclic molecule's
    // Bemis-Murcko scaffold is empty — so a linker or peptidomimetic series
    // lands in the no-scaffold bucket even when its members share a backbone.
    setTree(diverse);
    setMcs({ core_smiles: PYRIDINE, num_atoms: 15, molecule_count: 3 });
    render(
      <RGroupCorePicker moleculeIds={["a", "b", "c"]} coreSmiles={null} onCoreChange={vi.fn()} />,
    );

    expect(screen.getByTestId(`thumb-${PYRIDINE}`)).toBeInTheDocument();
    expect(screen.getByText(/No shared ring scaffold/i)).toBeInTheDocument();
    // Size is stated on the chip and again in the explanation — the chemist
    // needs it to tell a real backbone from a benzene without squinting.
    expect(screen.getAllByText(/15 atoms/).length).toBe(2);
    // Not the amber "nothing here" panel — this set does share something.
    expect(screen.queryByText(/No shared scaffold across/i)).not.toBeInTheDocument();
  });
});
