import { TooltipProvider } from "@/shared/components/ui/tooltip";
import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { createRef, useEffect } from "react";
import { describe, expect, it, vi } from "vitest";
import { crossProtocol } from "../lib/cross-protocol-fixture";
import type { Filter } from "../lib/filters";
import { provenanceOf } from "../lib/traces/test-fixtures";
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
  provenance: provenanceOf(key),
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
    "rd:s:raw:q": [">", null, "<="],
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
    onOpenCurves = vi.fn(),
  }: {
    filters?: Filter[];
    table?: Dataset;
    ref?: React.Ref<WorkbenchTableHandle>;
    onOpenCurves?: (key: string, i: number) => void;
  } = {},
) =>
  render(
    // The dashboard layout's sidebar provides tooltips in the app.
    <TooltipProvider>
      <WorkbenchProvider initialPanels={[]} initialFilters={filters}>
        <Seed ids={selected} />
        <div style={{ height: 600 }}>
          <WorkbenchTable ds={table} ref={ref} onOpenCurves={onOpenCurves} />
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
    expect(screen.getByText("≤ 3")).toBeInTheDocument();
    expect(screen.getByText("40")).toHaveClass("line-through");
    expect(screen.getByText("Negative control")).toBeInTheDocument();
  });

  it("keeps rows in the DOM in their shown order, so Tab follows a sort", async () => {
    const shuffled: Dataset = {
      ...ds,
      values: {
        ...ds.values,
        compound: ["CEL-2", "CEL-1", "CEL-3"],
        molecule_id: ["m2", "m1", "m3"],
      },
    };
    const { container } = show([], { table: shuffled });
    await screen.findByRole("link", { name: "CEL-1" });
    const header = container.querySelector('.ag-header-cell[col-id="compound"]');
    fireEvent.click(header?.querySelector(".ag-header-cell-label") as Element);
    await vi.waitFor(() =>
      expect(screen.getAllByRole("link").map((a) => a.textContent)).toEqual([
        "CEL-1",
        "CEL-2",
        "CEL-3",
      ]),
    );
  });

  it("ranks compared values with missing ones last both ways, saying why they are missing", async () => {
    const ranked: Dataset = {
      ...crossProtocol,
      values: {
        ...crossProtocol.values,
        "dr:y:p": [5, null, 6],
        "sel:dr:x:p|dr:y:p": [2, null, 0.5],
      },
    };
    const ref = createRef<WorkbenchTableHandle>();
    const { container } = show([], { table: ranked, ref });
    await screen.findByText("C1");
    // Protocol names head their groups; the columns under them drop the prefix.
    const headers = [...container.querySelectorAll(".ag-header-group-text, .ag-header-cell-text")];
    expect(headers.map((h) => h.textContent).filter(Boolean)).toEqual([
      "Compound",
      "Primary",
      "Counter",
      "Selectivity",
      "pIC50",
      "pIC50",
      "Tested in Counter",
      "Δ (Primary · pIC50) − (Counter · pIC50)",
    ]);
    // C2 in Counter and its Δ.
    expect(screen.getAllByText("not tested in Counter")).toHaveLength(2);
    const sel = container.querySelector('.ag-header-cell[col-id="sel:dr:x:p|dr:y:p"]');
    const order = () => screen.getAllByText(/^C\d$/).map((c) => c.textContent);
    fireEvent.click(sel?.querySelector(".ag-header-cell-label") as Element);
    await vi.waitFor(() => expect(order()).toEqual(["C3", "C1", "C2"]));
    fireEvent.click(sel?.querySelector(".ag-header-cell-label") as Element);
    await vi.waitFor(() => expect(order()).toEqual(["C1", "C3", "C2"]));
    // The export keeps each column's full label.
    expect((await exportedCsv(ref))[0]).toBe(
      '"Compound","Primary · pIC50","Counter · pIC50","Tested in Counter","Δ (Primary · pIC50) − (Counter · pIC50)"',
    );
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

  // A Compounds dataset as the server sends it: values with their stat siblings.
  const mean = { protocol_id: "P1", readout_definition_id: "s", layer: "raw", aggregation: "mean" };
  const geo = {
    protocol_id: "P1",
    readout_definition_id: "e",
    layer: null,
    aggregation: "geomean",
  };
  const compounds: Dataset = {
    revision: "c",
    level: "compounds",
    row_count: 2,
    row_ids: ["m1", "m2"],
    columns: [
      col("compound", "category", { label: "Compound" }),
      col("structure", "structure", { label: "Structure" }),
      col("molecule_id", "text", { hidden: true }),
      col("rd:s:raw", "number", { label: "Signal (%)", group: "Signal", provenance: mean }),
      col("rd:s:raw:q", "category", {
        label: "Signal (%) qualifier",
        group: "Signal",
        provenance: { ...mean, stat: "qualifier" },
      }),
      col("rd:s:raw:n", "number", {
        label: "Signal (%) n",
        group: "Signal",
        provenance: { ...mean, stat: "n" },
      }),
      col("rd:s:raw:sd", "number", {
        label: "Signal (%) SD",
        group: "Signal",
        provenance: { ...mean, stat: "sd" },
      }),
      col("rd:s:raw:n_censored", "number", {
        label: "Signal (%) n censored",
        group: "Signal",
        provenance: { ...mean, stat: "n_censored" },
      }),
      col("dr:e", "number", { label: "Enzyme · IC50", group: "Enzyme", provenance: geo }),
      col("dr:e:p", "number", {
        label: "Enzyme · pIC50",
        group: "Enzyme",
        provenance: { ...geo, aggregation: "p" },
      }),
      ...["n_tested", "n_inactive", "n_used"].map((stat) =>
        col(`dr:e:${stat}`, "number", {
          label: `Enzyme · IC50 ${stat}`,
          group: "Enzyme",
          provenance: { ...geo, stat },
        }),
      ),
      col("mw", "number", { label: "MW", group: "Descriptors" }),
    ],
    values: {
      compound: ["CEL-1", "CEL-2"],
      structure: ["CCO", "c1ccccc1"],
      molecule_id: ["m1", "m2"],
      "rd:s:raw": [15, 80],
      "rd:s:raw:q": [null, ">"],
      "rd:s:raw:n": [2, 0],
      "rd:s:raw:sd": [7.07, null],
      "rd:s:raw:n_censored": [1, 2],
      "dr:e": [0.5, null],
      "dr:e:p": [6.30103, null],
      "dr:e:n_tested": [3, null],
      "dr:e:n_inactive": [1, null],
      "dr:e:n_used": [2, null],
      mw: [300.1, 410.2],
    },
  };

  it("folds aggregated siblings into their values: not columns, not exported", async () => {
    const ref = createRef<WorkbenchTableHandle>();
    show([], { table: compounds, ref });
    await screen.findByRole("link", { name: "CEL-1" });
    expect(screen.getByText("Inactive 1/3 curves")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /> 80/ })).toBeInTheDocument();
    expect(await exportedCsv(ref)).toEqual([
      '"Compound","Structure","Signal (%)","Enzyme · IC50","Enzyme · pIC50","MW"',
      '"CEL-1","CCO","15","0.5","6.30103","300.1"',
      '"CEL-2","c1ccccc1",">80","","","410.2"',
    ]);
    fireEvent.keyDown(screen.getByRole("button", { name: "Columns" }), { key: "Enter" });
    expect(screen.getByRole("menuitemcheckbox", { name: "Enzyme · pIC50" })).toBeInTheDocument();
    expect(
      screen.queryByRole("menuitemcheckbox", { name: /Signal \(%\) n|SD|n_tested/ }),
    ).toBeNull();
  });

  it("opens a compound's curves from its Curves (n) button", async () => {
    const onOpenCurves = vi.fn();
    show([], { table: compounds, onOpenCurves });
    fireEvent.click(await screen.findByRole("button", { name: "Curves (3)" }));
    expect(onOpenCurves).toHaveBeenCalledWith("dr:e", 0);
    // Only rows with curves get the button.
    expect(screen.getAllByRole("button", { name: /^Curves/ })).toHaveLength(1);
  });
});
