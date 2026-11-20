import { TooltipProvider } from "@/shared/components/ui/tooltip";
import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { type ReactNode, createRef, useEffect } from "react";
import { describe, expect, it, onTestFinished, vi } from "vitest";
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
    extra,
  }: {
    filters?: Filter[];
    table?: Dataset;
    ref?: React.Ref<WorkbenchTableHandle>;
    onOpenCurves?: (key: string, i: number) => void;
    /** Rendered inside the provider, beside the table. */
    extra?: ReactNode;
  } = {},
) =>
  render(
    // The dashboard layout's sidebar provides tooltips in the app.
    <TooltipProvider>
      <WorkbenchProvider initialPanels={[]} initialFilters={filters}>
        <Seed ids={selected} />
        {extra}
        <WorkbenchTable ds={table} ref={ref} onOpenCurves={onOpenCurves} />
      </WorkbenchProvider>
    </TooltipProvider>,
  );

function ApplyFilters({ filters }: { filters: Filter[] }) {
  const setFilters = useWorkbench((s) => s.setFilters);
  return (
    <button type="button" onClick={() => setFilters(filters)}>
      Apply filters
    </button>
  );
}

/** ``n`` sample wells: the first 150 samples, the rest blanks. */
const many = (n: number): Dataset => {
  const rowIds = Array.from({ length: n }, (_, i) => `w${i}`);
  return {
    ...ds,
    row_count: n,
    row_ids: rowIds,
    columns: [
      col("compound", "category"),
      col("molecule_id", "text", { hidden: true }),
      col("well_type", "category"),
    ],
    values: {
      compound: rowIds.map((_, i) => `CEL-${i}`),
      molecule_id: rowIds.map((_, i) => `m${i}`),
      well_type: rowIds.map((_, i) => (i < 150 ? "sample" : "blank")),
    },
  };
};

const pageSummary = () =>
  document.querySelector(".ag-paging-row-summary-panel")?.textContent?.replace(/\s+/g, " ").trim();

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

  it("links compounds and shows qualifiers and outliers", async () => {
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
    expect(screen.getByText("40")).toBeInTheDocument();
    expect(screen.getByText("Outlier")).toBeInTheDocument();
  });

  it("names a well without a compound by its label, else its role", async () => {
    const roles: Dataset = {
      ...ds,
      row_count: 4,
      row_ids: ["w0", "w1", "w2", "w3"],
      columns: [...ds.columns.slice(0, 4), col("label", "text")],
      values: {
        compound: ["RIF-1", null, null, null],
        structure: ["CCO", "", null, ""],
        molecule_id: ["m9", null, null, null],
        well_type: ["positive_control", "negative_control", "reference", "sample"],
        label: [null, null, "MadR", null],
      },
    };
    show([], { table: roles });
    // A control that names a batch keeps its compound.
    expect(await screen.findByRole("link", { name: "RIF-1" })).toBeInTheDocument();
    const cell = (row: string, key: string) =>
      document.querySelector(`[row-id="${row}"] [col-id="${key}"]`) as HTMLElement;
    expect(cell("w0", "structure")).toHaveTextContent("structure CCO");
    for (const [row, text] of [
      ["w1", "Negative control"],
      ["w2", "MadR"],
      ["w3", "no compound"],
    ]) {
      expect(within(cell(row, "compound")).getByText(text)).toBeInTheDocument();
      expect(within(cell(row, "structure")).getByText("no compound")).toBeInTheDocument();
    }
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
    expect(screen.getAllByTitle("Not tested in Counter")).toHaveLength(2);
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

  it("pages 100 rows at a time, 50 to 500 on offer", async () => {
    show([], { table: many(250) });
    await vi.waitFor(() => expect(pageSummary()).toBe("1 to 100 of 250"));
    fireEvent.mouseDown(screen.getByRole("combobox", { name: "Page Size" }));
    expect(screen.getAllByRole("option").map((o) => o.textContent?.trim())).toEqual([
      "50",
      "100",
      "250",
      "500",
    ]);
  });

  const samples: Filter = {
    id: "s",
    kind: "category",
    key: "well_type",
    values: ["sample"],
    includeMissing: false,
  };

  it("starts over at page 1 when the filters take the current page away", async () => {
    show([], { table: many(250), extra: <ApplyFilters filters={[samples]} /> });
    await vi.waitFor(() => expect(pageSummary()).toBe("1 to 100 of 250"));
    fireEvent.click(screen.getByRole("button", { name: "Last Page" }));
    await vi.waitFor(() => expect(pageSummary()).toBe("201 to 250 of 250"));
    fireEvent.click(screen.getByRole("button", { name: "Apply filters" }));
    await vi.waitFor(() => expect(pageSummary()).toBe("1 to 100 of 150"));
  });

  it("keeps the current page while it still exists", async () => {
    show([], { table: many(250), extra: <ApplyFilters filters={[samples]} /> });
    await vi.waitFor(() => expect(pageSummary()).toBe("1 to 100 of 250"));
    fireEvent.click(screen.getByRole("button", { name: "Next Page" }));
    await vi.waitFor(() => expect(pageSummary()).toBe("101 to 200 of 250"));
    fireEvent.click(screen.getByRole("button", { name: "Apply filters" }));
    await vi.waitFor(() => expect(pageSummary()).toBe("101 to 150 of 150"));
  });

  it("lands on the new page's first row, under the header, not on the Selected block", async () => {
    const { container } = show(["w0"], { table: many(250) });
    await vi.waitFor(() => expect(pageSummary()).toBe("1 to 100 of 249"));
    const table = container.querySelector(".viz-table") as HTMLElement;
    const body = container.querySelector(".ag-body") as HTMLElement;
    const header = container.querySelector(".ag-header") as HTMLElement;
    table.scrollIntoView = vi.fn();
    body.scrollIntoView = vi.fn();
    // Scrolled to the foot of the page: the header sticks at the top, the rows began far above.
    vi.spyOn(header, "getBoundingClientRect").mockReturnValue({
      bottom: 64,
      height: 64,
    } as DOMRect);
    vi.spyOn(body, "getBoundingClientRect").mockReturnValue({ top: -9000 } as DOMRect);
    fireEvent.click(screen.getByRole("button", { name: "Next Page" }));
    await vi.waitFor(() => expect(body.scrollIntoView).toHaveBeenCalledWith({ block: "start" }));
    expect(body.style.scrollMarginTop).toBe("64px");
    expect(table.scrollIntoView).not.toHaveBeenCalled();
  });

  it("stays put when the new page's first row is already in view", async () => {
    const { container } = show([], { table: many(250) });
    await vi.waitFor(() => expect(pageSummary()).toBe("1 to 100 of 250"));
    const body = container.querySelector(".ag-body") as HTMLElement;
    const header = container.querySelector(".ag-header") as HTMLElement;
    body.scrollIntoView = vi.fn();
    vi.spyOn(header, "getBoundingClientRect").mockReturnValue({
      bottom: 300,
      height: 64,
    } as DOMRect);
    vi.spyOn(body, "getBoundingClientRect").mockReturnValue({ top: 300 } as DOMRect);
    fireEvent.click(await screen.findByRole("button", { name: "Next page" }));
    await vi.waitFor(() => expect(pageSummary()).toBe("101 to 200 of 250"));
    expect(body.scrollIntoView).not.toHaveBeenCalled();
  });

  it("pages from the toolbar too, in step with the pager below", async () => {
    show([], { table: many(250) });
    await vi.waitFor(() => expect(pageSummary()).toBe("1 to 100 of 250"));
    // The toolbar learns the page count a render after the grid's own pager.
    const pages = await screen.findByRole("group", { name: "Pages" });
    expect(pages).toHaveTextContent("Page 1 of 3");
    expect(within(pages).getByRole("button", { name: "Previous page" })).toBeDisabled();
    fireEvent.click(within(pages).getByRole("button", { name: "Next page" }));
    await vi.waitFor(() => expect(pageSummary()).toBe("101 to 200 of 250"));
    await vi.waitFor(() => expect(pages).toHaveTextContent("Page 2 of 3"));
    fireEvent.click(screen.getByRole("button", { name: "Last Page" }));
    await vi.waitFor(() => expect(pages).toHaveTextContent("Page 3 of 3"));
    expect(within(pages).getByRole("button", { name: "Next page" })).toBeDisabled();
  });

  it("offers no toolbar pager for a single page", async () => {
    show();
    await screen.findByRole("link", { name: "CEL-1" });
    expect(screen.queryByRole("group", { name: "Pages" })).toBeNull();
  });

  it("counts the rows as the pager does, the pinned selected ones apart", async () => {
    show(["w0", "w1"], { table: many(250) });
    await vi.waitFor(() => expect(pageSummary()).toBe("1 to 100 of 248"));
    expect(screen.getByText("248 rows + 2 selected")).toBeInTheDocument();
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
      '"Compound","Structure","well_type","rd:s:raw","rd:s:raw qualifier"',
      '"CEL-1","CCO","Sample","12.3456",">"',
    ]);
  });

  it("exports every passing row when nothing is selected", async () => {
    const ref = createRef<WorkbenchTableHandle>();
    show([], { filters: [controls], table: precise, ref });
    await screen.findByRole("link", { name: "CEL-1" });
    expect(await exportedCsv(ref)).toEqual([
      '"Compound","Structure","well_type","rd:s:raw","rd:s:raw qualifier"',
      '"CEL-1","CCO","Sample","12.3456",">"',
      '"CEL-2","c1ccccc1","Sample","40",""',
    ]);
  });

  it("exports plain numbers, each bound in a qualifier column beside its value", async () => {
    // A number with "=" in front reads as a formula in Excel and as text in pandas or R.
    const ref = createRef<WorkbenchTableHandle>();
    const bounds = { ...precise, values: { ...precise.values, "rd:s:raw:q": [">", "=", "<="] } };
    show([], { table: bounds, ref });
    await screen.findByRole("link", { name: "CEL-1" });
    expect(await exportedCsv(ref)).toEqual([
      '"Compound","Structure","well_type","rd:s:raw","rd:s:raw qualifier"',
      '"CEL-1","CCO","Sample","12.3456",">"',
      '"CEL-2","c1ccccc1","Sample","40",""',
      '"","","Negative control","3","≤"',
    ]);
    // On screen the bound stays in front of its number, with no column of its own.
    expect(screen.getByText("> 12.3")).toBeInTheDocument();
    expect(document.querySelector('.ag-header-cell[col-id="rd:s:raw:q"]')).toBeNull();
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
      '"Compound","Structure","Signal (%)","Signal (%) qualifier","Enzyme · IC50","Enzyme · pIC50","MW"',
      '"CEL-1","CCO","15","","0.5","6.30103","300.1"',
      '"CEL-2","c1ccccc1","80",">","","","410.2"',
    ]);
    fireEvent.keyDown(screen.getByRole("button", { name: "Columns" }), { key: "Enter" });
    expect(screen.getByRole("menuitemcheckbox", { name: "Enzyme · pIC50" })).toBeInTheDocument();
    expect(
      screen.queryByRole("menuitemcheckbox", { name: /Signal \(%\) n|SD|n_tested/ }),
    ).toBeNull();
  });

  /** Presses Tab (Shift+Tab) on the focused element; returns what holds focus after it. */
  const tab = (shiftKey = false) => {
    fireEvent.keyDown(document.activeElement as Element, { key: "Tab", shiftKey });
    return document.activeElement;
  };
  const nameOf = (el: Element | null) =>
    el?.getAttribute("aria-label")?.split(",")[0] ?? el?.textContent?.trim();
  const walk = (steps: number, shiftKey = false) =>
    Array.from({ length: steps }, () => nameOf(tab(shiftKey)));
  const focusHeader = (colId: string) =>
    act(() =>
      (document.querySelector(`.ag-header-cell[col-id="${colId}"]`) as HTMLElement).focus(),
    );

  it("tabs from the header through each row's pinned and centre controls, then on to the pager", async () => {
    show([], { table: compounds });
    await screen.findByRole("link", { name: "CEL-1" });
    focusHeader("mw"); // the last column's header
    expect(walk(9)).toEqual([
      "Select row",
      "CEL-1",
      "15",
      "0.5",
      "Curves (3)",
      "6.3",
      "Select row",
      "CEL-2",
      "> 80",
    ]);
    // Past the last row: out of the rows, to the pager's first control.
    expect(tab()?.closest(".ag-paging-panel")).not.toBeNull();
    tab(true);
    expect(nameOf(document.activeElement)).toBe("> 80");
    expect(walk(8, true)).toEqual([
      "CEL-2",
      "Select row",
      "6.3",
      "Curves (3)",
      "0.5",
      "15",
      "CEL-1",
      "Select row",
    ]);
    // Before the first row: back to the last column's header.
    expect(tab(true)?.closest(".ag-header-cell")?.getAttribute("col-id")).toBe("mw");
  });

  it("tabs through the controls of columns beyond the visible width, row by row", async () => {
    // A table wider than its viewport: ten descriptors, then one more value at the far right.
    const tail = { ...mean, readout_definition_id: "t" };
    const wideCompounds: Dataset = {
      ...compounds,
      columns: [
        ...compounds.columns.filter((c) => c.key !== "mw"),
        ...Array.from({ length: 10 }, (_, k) => col(`d${k}`, "number", { group: "Descriptors" })),
        col("rd:t:raw", "number", { label: "Tail (%)", group: "Tail", provenance: tail }),
        col("rd:t:raw:n", "number", {
          label: "Tail (%) n",
          group: "Tail",
          provenance: { ...tail, stat: "n" },
        }),
      ],
      values: {
        ...compounds.values,
        ...Object.fromEntries(Array.from({ length: 10 }, (_, k) => [`d${k}`, [k, k]])),
        "rd:t:raw": [42, 7],
        "rd:t:raw:n": [2, 2],
      },
    };
    // The grid's centre viewport is 300 px wide (jsdom lays nothing out).
    const real = window.getComputedStyle.bind(window);
    const spy = vi.spyOn(window, "getComputedStyle").mockImplementation((el, pseudo) => {
      const style = real(el, pseudo);
      if (!el.classList.contains("ag-center-cols-viewport")) return style;
      return new Proxy(style, {
        get: (t, k) => {
          if (k === "width") return "300px";
          const v = Reflect.get(t, k);
          return typeof v === "function" ? v.bind(t) : v;
        },
      });
    });
    onTestFinished(() => spy.mockRestore());
    show([], { table: wideCompounds });
    await screen.findByRole("link", { name: "CEL-1" });
    act(() => screen.getAllByRole("checkbox", { name: "Select row" })[0].focus());
    expect(walk(10)).toEqual([
      "CEL-1",
      "15",
      "0.5",
      "Curves (3)",
      "6.3",
      "42",
      "Select row",
      "CEL-2",
      "> 80",
      "7",
    ]);
  });

  it("tabs from Selected (n) into the selected rows, then the page", async () => {
    show(["m2"], { table: compounds });
    const group = await screen.findByRole("button", { name: "Selected (1)" });
    act(() => group.focus());
    expect(walk(5)).toEqual(["Select row", "CEL-2", "> 80", "Select row", "CEL-1"]);
    expect(walk(5, true)).toEqual(["Select row", "> 80", "CEL-2", "Select row", "Selected (1)"]);
    expect(tab(true)?.closest(".ag-header-cell")?.getAttribute("col-id")).toBe("mw");
  });

  it("leaves arrows and Escape to the browser on cell and Selected-row buttons", async () => {
    show(["m1"], { table: compounds });
    const value = await screen.findByRole("button", { name: /> 80/ });
    const group = screen.getByRole("button", { name: "Selected (1)" });
    for (const target of [value, group]) {
      for (const key of ["ArrowRight", "ArrowDown", "Escape"]) {
        expect(fireEvent.keyDown(target, { key }), `${key} on ${target.textContent}`).toBe(true);
      }
    }
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
