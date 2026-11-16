import { TooltipProvider } from "@/shared/components/ui/tooltip";
import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { createRef, useEffect } from "react";
import { describe, expect, it, vi } from "vitest";
import type { Filter } from "../lib/filters";
import { WorkbenchProvider, useWorkbench } from "../store/workbench-context";
import type { Dataset, DatasetColumn } from "../types";
import { WorkbenchTable, type WorkbenchTableHandle } from "./workbench-table";

vi.mock("@/shared/components/chemistry", () => ({
  StructureThumbnail: ({ smiles }: { smiles: string }) => <span>structure {smiles}</span>,
}));

const col = (key: string, kind: DatasetColumn["kind"], extra = {}): DatasetColumn => ({
  key,
  label: key,
  kind,
  provenance: {},
  ...extra,
});

const ds: Dataset = {
  revision: "r",
  level: "wells",
  row_count: 3,
  row_ids: ["w0", "w1", "w2"],
  columns: [
    col("compound", "category"),
    col("structure", "structure"),
    col("molecule_id", "text", { hidden: true }),
    col("well_type", "category"),
    col("rd:s:raw", "number", { group: "Signal" }),
    col("rd:s:raw:q", "category", { group: "Signal" }),
    col("rd:s:raw:outlier", "category", { group: "Signal" }),
  ],
  values: {
    compound: ["CEL-1", "CEL-2", null],
    structure: ["CCO", "c1ccccc1", ""],
    molecule_id: ["m1", "m2", null],
    well_type: ["sample", "sample", "negative_control"],
    "rd:s:raw": [12.5, 40, 3],
    "rd:s:raw:q": [">", null, null],
    "rd:s:raw:outlier": [null, "outlier", null],
  },
};

function Seed({ ids }: { ids: string[] }) {
  const setSelection = useWorkbench((s) => s.setSelection);
  // biome-ignore lint/correctness/useExhaustiveDependencies: seed once on mount
  useEffect(() => setSelection(ids), []);
  return null;
}

const show = (
  selected: string[] = [],
  {
    filters,
    table = ds,
    ref,
  }: { filters?: Filter[]; table?: Dataset; ref?: React.Ref<WorkbenchTableHandle> } = {},
) =>
  render(
    // The dashboard layout's sidebar provides tooltips in the app.
    <TooltipProvider>
      <WorkbenchProvider initialPanels={[]} initialFilters={filters}>
        <Seed ids={selected} />
        <div style={{ height: 600 }}>
          <WorkbenchTable ds={table} ref={ref} />
        </div>
      </WorkbenchProvider>
    </TooltipProvider>,
  );

describe("WorkbenchTable", () => {
  it("links compounds, leaves control wells blank, and shows qualifiers and outliers", async () => {
    show();
    expect(await screen.findByRole("link", { name: "CEL-1" })).toHaveAttribute(
      "href",
      "/compounds/m1",
    );
    expect(screen.getAllByRole("link")).toHaveLength(2);
    expect(screen.getByText("structure CCO")).toBeInTheDocument();
    expect(screen.queryByText(/structure $/)).not.toBeInTheDocument();
    expect(screen.getByText("> 12.5")).toBeInTheDocument();
    expect(screen.getByText("40")).toHaveClass("line-through");
    expect(screen.getByText("Negative control")).toBeInTheDocument();
  });

  it("drops structures in compact density", async () => {
    show();
    await screen.findByText("structure CCO");
    fireEvent.click(screen.getByRole("button", { name: "Compact" }));
    expect(screen.queryByText("structure CCO")).not.toBeInTheDocument();
  });

  it("pins selected rows under a collapsible Selected (n) row", async () => {
    show(["w1"]);
    const group = await screen.findByRole("button", { name: "Selected (1)" });
    const pinned = document.querySelector(".ag-floating-top") as HTMLElement;
    expect(within(pinned).getByRole("link", { name: "CEL-2" })).toBeInTheDocument();
    fireEvent.click(group);
    expect(within(pinned).queryByRole("link", { name: "CEL-2" })).not.toBeInTheDocument();
  });

  it("exports visible columns and passing rows as CSV, numbers unrounded", async () => {
    const blobs: Blob[] = [];
    URL.createObjectURL = vi.fn((b: Blob) => {
      blobs.push(b);
      return "blob:csv";
    });
    URL.revokeObjectURL = vi.fn();
    const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
    const ref = createRef<WorkbenchTableHandle>();
    const precise = { ...ds, values: { ...ds.values, "rd:s:raw": [12.3456, 40, 3] } };
    const controls: Filter = {
      id: "f",
      kind: "category",
      key: "well_type",
      values: ["sample"],
      includeMissing: false,
    };
    show(["w1"], { filters: [controls], table: precise, ref });
    // The collapsed Selected group still exports its rows.
    fireEvent.click(await screen.findByRole("button", { name: "Selected (1)" }));
    act(() => ref.current?.exportCsv("wells.csv"));
    expect(blobs).toHaveLength(1);
    expect(click).toHaveBeenCalledTimes(1);
    click.mockRestore();
    // jsdom's Blob has no text(); FileReader reads it.
    const csv = await new Promise<string>((resolve) => {
      const reader = new FileReader();
      reader.onload = () => resolve(String(reader.result));
      reader.readAsText(blobs[0]);
    });
    const lines = csv.split(/\r?\n/);
    expect(lines).toEqual([
      '"Compound","Structure","well_type","rd:s:raw"',
      '"CEL-2","c1ccccc1","Sample","40"',
      '"CEL-1","CCO","Sample",">12.3456"',
    ]);
  });
});
