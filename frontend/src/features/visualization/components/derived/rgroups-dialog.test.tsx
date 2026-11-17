import type { UseMcsReturn } from "@/features/sar-analysis/hooks/use-mcs";
import type { UseScaffoldTreeReturn } from "@/features/sar-analysis/hooks/use-scaffold-tree";
import type { ScaffoldTreeResult } from "@/features/sar-analysis/types";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

const h = vi.hoisted(() => ({
  tree: null as unknown as UseScaffoldTreeReturn,
  treeInput: undefined as unknown,
}));

vi.mock("@/features/sar-analysis/hooks/use-scaffold-tree", () => ({
  useScaffoldTree: (input: unknown): UseScaffoldTreeReturn => {
    h.treeInput = input;
    return h.tree;
  },
}));
vi.mock("@/features/sar-analysis/hooks/use-mcs", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/features/sar-analysis/hooks/use-mcs")>()),
  useMcs: (): UseMcsReturn => ({ mcs: null, isLoading: false, error: null, outOfRange: false }),
}));
// RDKit/Ketcher-free shim.
vi.mock("@/shared/components/chemistry", () => ({
  StructureThumbnail: ({ smiles }: { smiles: string }) => <div data-testid={`thumb-${smiles}`} />,
  StructureEditorDialog: () => null,
}));

import { RGroupsDialog } from "./rgroups-dialog";

const IDS = ["m1", "m2", "m3", "m4"];
const node = (scaffold_smiles: string, molecule_ids: string[]) => ({
  scaffold_smiles,
  molecule_ids,
  molecule_count: molecule_ids.length,
  subtree_molecule_count: molecule_ids.length,
});
// Benzene is in all four (pyridine's three hang under it); pyridine in three.
const tree: ScaffoldTreeResult = {
  nodes: [node("c1ccccc1", ["m4"]), node("c1ccncc1", ["m1", "m2", "m3"])],
  edges: [{ parent_smiles: "c1ccccc1", child_smiles: "c1ccncc1" }],
  stats: { node_count: 2, elapsed_ms: 1, cache_hit: false },
};
const setTree = (t: ScaffoldTreeResult | null) => {
  h.tree = { tree: t, jobId: null, isStarting: false, isPolling: false, error: null };
};

const open = () => {
  const onApply = vi.fn();
  const onOpenChange = vi.fn();
  render(<RGroupsDialog open onOpenChange={onOpenChange} moleculeIds={IDS} onApply={onApply} />);
  return { onApply, onOpenChange };
};
const apply = () => screen.getByRole("button", { name: "Add R-group columns" });

describe("RGroupsDialog", () => {
  it("decomposes the dataset's compounds against the core picked in the SAR core picker", () => {
    setTree(tree);
    const { onApply, onOpenChange } = open();
    expect(h.treeInput).toMatchObject({ moleculeIds: IDS });
    expect(screen.getByText("Decompose 4 compounds against this core")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Select core c1ccncc1/ }));
    fireEvent.click(apply());
    expect(onApply).toHaveBeenCalledWith("c1ccncc1");
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  it("cannot apply without a core", () => {
    // No scaffold is shared by three compounds: nothing is suggested.
    setTree({ ...tree, nodes: [node("c1ccccc1", ["m1"]), node("C1CCCCC1", ["m2"])], edges: [] });
    const { onApply } = open();
    expect(apply()).toBeDisabled();
    fireEvent.click(apply());
    expect(onApply).not.toHaveBeenCalled();
  });

  it("fits the screen: the core picker scrolls between title and footer", () => {
    setTree(tree);
    open();
    expect(screen.getByRole("dialog")).toHaveClass("max-h-[calc(100dvh-2rem)]", "flex-col");
    const picker = screen
      .getByRole("button", { name: /Select core c1ccncc1/ })
      .closest(".overflow-y-auto");
    expect(picker).toHaveClass("min-h-0");
    expect(picker).not.toContainElement(apply());
  });
});
