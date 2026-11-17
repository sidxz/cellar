import type { UseScaffoldTreeReturn } from "@/features/sar-analysis/hooks/use-scaffold-tree";
import type { ScaffoldTreeResult } from "@/features/sar-analysis/types";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { SeriesMember } from "../../lib/derived";
import { rgroupSet } from "../../lib/derived";
import { dataset } from "../../lib/traces/test-fixtures";

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
vi.mock("@/shared/components/chemistry", () => ({
  StructureThumbnail: ({ smiles }: { smiles: string }) => <div data-testid={`thumb-${smiles}`} />,
}));

import { SeriesDialog } from "./series-dialog";

// m1–m4 have structures, m5 none.
const ds = dataset(
  {
    molecule_id: ["m1", "m2", "m3", "m4", "m5"],
    structure: ["c1ccccc1C", "c1ccncc1", "c1ccncc1C", "c1ccncc1N", null],
  },
  { structure: "structure" },
);
const IDS = ["m1", "m2", "m3", "m4"];
const node = (scaffold_smiles: string, molecule_ids: string[]) => ({
  scaffold_smiles,
  molecule_ids,
  molecule_count: molecule_ids.length,
  subtree_molecule_count: molecule_ids.length,
});
// S1 contains S2: S1 is in all four compounds, S2 in three.
const tree: ScaffoldTreeResult = {
  nodes: [node("S1", ["m1"]), node("S2", ["m2", "m3", "m4"])],
  edges: [{ parent_smiles: "S1", child_smiles: "S2" }],
  stats: { node_count: 2, elapsed_ms: 1, cache_hit: false },
};
const coreA = rgroupSet(
  { id: "rg1", kind: "rgroups", coreSmiles: "c1ccccc1", name: "Core A" },
  ds,
  {
    core_smiles: "c1ccccc1",
    labels: ["R1"],
    assignments: { m1: { R1: "C[*:1]" } },
  },
);
const setTree = (t: ScaffoldTreeResult | null, more: Partial<UseScaffoldTreeReturn> = {}) => {
  h.tree = { tree: t, jobId: null, isStarting: false, isPolling: false, error: null, ...more };
};

const open = (initial?: SeriesMember[]) => {
  const onApply = vi.fn();
  const onOpenChange = vi.fn();
  render(
    <SeriesDialog
      open
      onOpenChange={onOpenChange}
      ds={ds}
      moleculeIds={IDS}
      rgroupSets={[coreA]}
      initial={initial}
      onApply={onApply}
    />,
  );
  return { onApply, onOpenChange };
};
const apply = () => screen.getByRole("button", { name: "Add series column" });
const scaffoldTiles = () => screen.getAllByRole("button", { name: /^Scaffold/ });
const coreTile = () => screen.getByRole("button", { name: "R-group core · Core A · 1 match" });

describe("SeriesDialog", () => {
  it("offers the shared scaffolds and each R-group core, naming picks Series A, B …", () => {
    setTree(tree);
    const { onApply, onOpenChange } = open();
    expect(h.treeInput).toMatchObject({ moleculeIds: IDS });
    expect(scaffoldTiles().map((b) => b.getAttribute("aria-label"))).toEqual([
      "Scaffold of 4 compounds: S1",
      "Scaffold of 3 compounds: S2",
    ]);
    expect(apply()).toBeDisabled();

    fireEvent.click(scaffoldTiles()[1]);
    fireEvent.click(coreTile());
    expect(screen.getByLabelText("Series 1 name")).toHaveValue("Series A");
    expect(screen.getByLabelText("Series 2 name")).toHaveValue("Series B");
    // A source already used is not offered twice.
    expect(coreTile()).toBeDisabled();
    // Live preview: m2–m4 under S2, m1 matches Core A.
    expect(
      screen.getByText("Series A 3 · Series B 1 · Other 0 · 1 without a structure"),
    ).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Series 1 name"), { target: { value: "Pyridines" } });
    fireEvent.click(apply());
    expect(onApply).toHaveBeenCalledWith([
      { name: "Pyridines", scaffold: "S2" },
      { name: "Series B", rgroupsId: "rg1" },
    ]);
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  it("says what each count means, so one ring can count more as a core than as a scaffold", () => {
    setTree(tree);
    open();
    expect(screen.getByText("Scaffold of 3 compounds")).toBeInTheDocument();
    expect(scaffoldTiles()[1]).toHaveAttribute(
      "title",
      "3 compounds are built on this ring scaffold\nS2",
    );
    expect(coreTile()).toHaveAttribute("title", "1 compound contains this core\nc1ccccc1");
    expect(
      screen.getByText(
        "A scaffold counts the compounds built on it; a core counts every compound containing it, so the same ring can count more as a core.",
        { exact: false },
      ),
    ).toBeInTheDocument();
  });

  it("previews overlaps and removes a member", () => {
    setTree(tree);
    open();
    fireEvent.click(scaffoldTiles()[0]);
    fireEvent.click(coreTile());
    expect(
      screen.getByText("1 compound is in more than one series; it counts in the first"),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Remove Series A" }));
    expect(screen.getByLabelText("Series 1 name")).toHaveValue("Series B");
    // The freed letter is used again.
    fireEvent.click(scaffoldTiles()[0]);
    expect(screen.getByLabelText("Series 2 name")).toHaveValue("Series A");
  });

  it("refuses blank or repeated names", () => {
    setTree(tree);
    open([
      { name: "Series A", scaffold: "S1" },
      { name: "Series B", rgroupsId: "rg1" },
    ]);
    fireEvent.change(screen.getByLabelText("Series 2 name"), { target: { value: "Series A" } });
    expect(apply()).toBeDisabled();
    expect(screen.getByText("Give each series its own name.")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Series 2 name"), { target: { value: " " } });
    expect(apply()).toBeDisabled();
  });

  it("stops at 8 series", () => {
    const many: ScaffoldTreeResult = {
      nodes: Array.from({ length: 9 }, (_, k) => node(`S${k}`, [`a${k}`, `b${k}`, `c${k}`])),
      edges: [],
      stats: { node_count: 9, elapsed_ms: 1, cache_hit: false },
    };
    setTree(many);
    open();
    for (const tile of scaffoldTiles()) fireEvent.click(tile);
    expect(screen.getByLabelText("Series 8 name")).toHaveValue("Series H");
    expect(screen.queryByLabelText("Series 9 name")).not.toBeInTheDocument();
    expect(screen.getByText("Up to 8 series.")).toBeInTheDocument();
    expect(coreTile()).toBeDisabled();
  });

  it("guides the chemist to R-group cores when no scaffold is shared by 3 compounds", () => {
    setTree({ ...tree, nodes: [node("S1", ["m1"]), node("S2", ["m2"])], edges: [] });
    open();
    expect(
      screen.getByText(
        "No scaffold is shared by 3 or more compounds. Add R-groups with a drawn core and use it here.",
      ),
    ).toBeInTheDocument();
    expect(screen.queryAllByRole("button", { name: /^Scaffold/ })).toEqual([]);
    expect(coreTile()).toBeEnabled();
  });

  it("says while the scaffolds load, and when they fail", () => {
    setTree(null, { isStarting: true });
    const { unmount } = render(
      <SeriesDialog
        open
        onOpenChange={vi.fn()}
        ds={ds}
        moleculeIds={IDS}
        rgroupSets={[]}
        onApply={vi.fn()}
      />,
    );
    expect(screen.getByText("Finding scaffolds…")).toBeInTheDocument();
    unmount();
    setTree(null, { error: new Error("boom") });
    open();
    expect(screen.getByText("Could not load scaffolds.")).toBeInTheDocument();
  });

  it("fits the screen: no taller than the viewport, the cards scroll between title and footer", () => {
    setTree(tree);
    open();
    expect(screen.getByRole("dialog")).toHaveClass("max-h-[calc(100dvh-2rem)]", "flex-col");
    const cards = scaffoldTiles()[0].parentElement as HTMLElement;
    expect(cards).toHaveClass("min-h-0", "overflow-y-auto");
    expect(cards).not.toContainElement(
      screen.getByRole("heading", { name: "Add a series column" }),
    );
    expect(cards).not.toContainElement(apply());
  });
});
