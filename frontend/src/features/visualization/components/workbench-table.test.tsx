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

/** Lines of the table's CSV export (the displayed columns, in order). */
async function exportedCsv(ref: React.RefObject<WorkbenchTableHandle | null>): Promise<string[]> {
  const blobs: Blob[] = [];
  URL.createObjectURL = vi.fn((b: Blob) => {
    blobs.push(b);
    return "blob:csv";
  });
  URL.revokeObjectURL = vi.fn();
  const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
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
  return csv.split(/\r?\n/);
}

// Identity columns in dataset order, readout values last (as the backend sends them).
const wide: Dataset = {
  revision: "w",
  level: "wells",
  row_count: 1,
  row_ids: ["w0"],
  columns: [
    col("compound", "category", { label: "Compound" }),
    col("structure", "structure", { label: "Structure" }),
    col("molecule_id", "text", { hidden: true }),
    col("batch", "category", { label: "Batch" }),
    col("run", "category", { label: "Run" }),
    col("run_date", "category", { label: "Run date" }),
    col("run_status", "category", { label: "Run status" }),
    col("plate", "category", { label: "Plate" }),
    col("well", "text", { label: "Well" }),
    col("well_row", "category", { label: "Row" }),
    col("well_column", "number", { label: "Column" }),
    col("well_order", "number", { label: "Well order" }),
    col("well_type", "category", { label: "Well type" }),
    col("dose", "number", { label: "Dose" }),
    col("label", "text", { label: "Well label" }),
    col("cond:NADP", "category", { label: "NADP", group: "Conditions" }),
    col("rd:s:raw", "number", { label: "Signal (AU)", group: "Signal" }),
  ],
  values: {
    compound: ["CEL-1"],
    structure: ["CCO"],
    molecule_id: ["m1"],
    batch: [null],
    run: ["2026-11-12"],
    run_date: ["2026-11-12"],
    run_status: ["approved"],
    plate: ["Plate 1"],
    well: ["B03"],
    well_row: ["B"],
    well_column: [3],
    well_order: [27],
    well_type: ["sample"],
    dose: [null],
    label: [""],
    "cond:NADP": ["+"],
    "rd:s:raw": [12],
  },
};

describe("WorkbenchTable", () => {
  it("puts readout values after well and well type; hides redundant and empty columns", async () => {
    const ref = createRef<WorkbenchTableHandle>();
    show([], { table: wide, ref });
    await screen.findByRole("link", { name: "CEL-1" });
    expect((await exportedCsv(ref))[0]).toBe(
      '"Compound","Structure","Well","Well type","Signal (AU)","Run","Plate","NADP"',
    );
  });

  it("shows and hides columns from the Columns menu", async () => {
    const ref = createRef<WorkbenchTableHandle>();
    show([], { table: wide, ref });
    await screen.findByRole("link", { name: "CEL-1" });
    fireEvent.keyDown(screen.getByRole("button", { name: "Columns" }), { key: "Enter" });
    const runDate = screen.getByRole("menuitemcheckbox", { name: "Run date" });
    expect(runDate).toHaveAttribute("aria-checked", "false");
    expect(screen.getByRole("menuitemcheckbox", { name: "Plate" })).toHaveAttribute(
      "aria-checked",
      "true",
    );
    fireEvent.click(runDate);
    fireEvent.click(screen.getByRole("menuitemcheckbox", { name: "Plate" }));
    expect((await exportedCsv(ref))[0]).toBe(
      '"Compound","Structure","Well","Well type","Signal (AU)","Run","Run date","NADP"',
    );
  });

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

  it("shows at most 50 selected rows, then offers Filter to selection for the rest", async () => {
    const n = 60;
    const rowIds = Array.from({ length: n }, (_, i) => `w${i}`);
    const sixty: Dataset = {
      ...ds,
      row_count: n,
      row_ids: rowIds,
      columns: [col("compound", "category"), col("molecule_id", "text", { hidden: true })],
      values: {
        compound: rowIds.map((_, i) => `CEL-${i}`),
        molecule_id: rowIds.map((_, i) => `m${i}`),
      },
    };
    show(rowIds, { table: sixty });
    await screen.findByRole("button", { name: "Selected (60)" });
    const pinned = document.querySelector(".ag-floating-top") as HTMLElement;
    expect(within(pinned).getAllByRole("link")).toHaveLength(50);
    expect(within(pinned).getByText("and 10 more selected")).toBeInTheDocument();
    fireEvent.click(within(pinned).getByRole("button", { name: "Filter to selection" }));
    expect(screen.queryByRole("button", { name: /Selected/ })).not.toBeInTheDocument();
    expect(screen.getByText("60 rows")).toBeInTheDocument();
  });

  const precise = { ...ds, values: { ...ds.values, "rd:s:raw": [12.3456, 40, 3] } };
  const controls: Filter = {
    id: "f",
    kind: "category",
    key: "well_type",
    values: ["sample"],
    includeMissing: false,
  };

  it("exports the selected passing rows as CSV over the visible columns, numbers unrounded", async () => {
    const ref = createRef<WorkbenchTableHandle>();
    show(["w0", "w2"], { filters: [controls], table: precise, ref });
    // The collapsed Selected group still exports its rows.
    fireEvent.click(await screen.findByRole("button", { name: "Selected (1)" }));
    expect(await exportedCsv(ref)).toEqual([
      '"Compound","Structure","well_type","rd:s:raw"',
      '"CEL-1","CCO","Sample",">12.3456"',
    ]);
  });

  it("exports every passing row when nothing is selected", async () => {
    const ref = createRef<WorkbenchTableHandle>();
    show([], { filters: [controls], table: precise, ref });
    await screen.findByRole("link", { name: "CEL-1" });
    expect(await exportedCsv(ref)).toEqual([
      '"Compound","Structure","well_type","rd:s:raw"',
      '"CEL-1","CCO","Sample",">12.3456"',
      '"CEL-2","c1ccccc1","Sample","40"',
    ]);
  });
});
