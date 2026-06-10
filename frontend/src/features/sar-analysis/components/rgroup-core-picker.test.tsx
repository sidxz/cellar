import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { UseScaffoldTreeReturn } from "../hooks/use-scaffold-tree";

// Mock the scaffold-tree hook with two ringed nodes (counts 3 and 1). The
// picker should rank by molecule_count DESC, auto-suggest the dominant one
// (benzene), and emit on click of any candidate.
vi.mock("../hooks/use-scaffold-tree", () => ({
  useScaffoldTree: (): UseScaffoldTreeReturn => ({
    tree: {
      nodes: [
        {
          scaffold_smiles: "c1ccncc1",
          molecule_ids: ["d"],
          molecule_count: 1,
          subtree_molecule_count: 1,
        },
        {
          scaffold_smiles: "c1ccccc1",
          molecule_ids: ["a", "b", "c"],
          molecule_count: 3,
          subtree_molecule_count: 3,
        },
      ],
      edges: [],
      stats: { node_count: 2, elapsed_ms: 1, cache_hit: false },
    },
    jobId: null,
    isStarting: false,
    isPolling: false,
    error: null,
  }),
}));

// RDKit-free shim for the chemistry barrel (StructureThumbnail uses WASM that
// jsdom can't run; StructureEditorDialog pulls in Ketcher). Same convention as
// scaffold-tree-view.test.tsx.
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

describe("RGroupCorePicker", () => {
  it("preselects the dominant scaffold and emits on change", () => {
    const onCoreChange = vi.fn();
    render(
      <RGroupCorePicker
        moleculeIds={["a", "b", "c", "d"]}
        coreSmiles={null}
        onCoreChange={onCoreChange}
      />,
    );

    // Auto-suggest fires once on mount with the dominant scaffold (count 3).
    expect(onCoreChange).toHaveBeenCalledWith("c1ccccc1");

    // Clicking the other candidate emits its SMILES.
    fireEvent.click(screen.getByText(/c1ccncc1/));
    expect(onCoreChange).toHaveBeenCalledWith("c1ccncc1");
  });

  it("shows matched/unmatched line when counts are provided", () => {
    render(
      <RGroupCorePicker
        moleculeIds={["a", "b", "c", "d"]}
        coreSmiles="c1ccccc1"
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
      <RGroupCorePicker moleculeIds={["a"]} coreSmiles="c1ccccc1" onCoreChange={onCoreChange} />,
    );
    fireEvent.click(screen.getByText(/Edit core/i));
    fireEvent.click(screen.getByTestId("apply-core"));
    expect(onCoreChange).toHaveBeenCalledWith("Nc1ccccc1");
  });
});
