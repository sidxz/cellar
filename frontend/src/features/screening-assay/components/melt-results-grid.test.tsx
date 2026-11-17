import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { TooltipProvider } from "@/shared/components/ui/tooltip";
import type { ApplicableRule } from "../lib/melt-hits";
import type { ResultRow } from "../lib/melt-results";

vi.mock("@/shared/components/chemistry/structure-thumbnail", () => ({
  StructureThumbnail: (p: { size: number; height?: number }) => (
    <div data-testid="structure" data-width={p.size} data-height={p.height ?? p.size} />
  ),
}));

let defs: any[] = [];
let height = 0;
/** Draw the grid itself, not only capture its columns. */
let drawGrid = false;
vi.mock("@/shared/components/data-grid/data-grid", async (importOriginal) => {
  const { DataGrid } =
    await importOriginal<typeof import("@/shared/components/data-grid/data-grid")>();
  return {
    DataGrid: (p: { columnDefs: any[]; rowData: unknown[]; height: number }) => {
      defs = p.columnDefs;
      height = p.height;
      // jsdom has no layout, so the real grid draws every row instead of a screenful.
      return drawGrid ? <DataGrid {...p} suppressRowVirtualisation /> : null;
    },
  };
});

import { EMPTY_SELECTION } from "../lib/curve-selection";
import { MeltResultsGrid } from "./melt-results-grid";

const row = {
  wellId: "w1",
  position: "Capillary 1",
  wellType: "sample",
  isSample: true,
  batchId: null,
  identity: {
    registrationNumber: null,
    moleculeId: null,
    batchSuffix: null,
    smiles: null,
    label: "Long sample",
    aliases: [],
  },
  sampleText: "Long sample",
  concentration: 1,
  cells: {},
} as unknown as ResultRow;

const show = (windowNames: string[], over: Partial<Parameters<typeof MeltResultsGrid>[0]> = {}) =>
  render(
    <MeltResultsGrid
      rows={{ pinned: [], body: [row] }}
      windowNames={windowNames}
      steps={[]}
      windows={[]}
      hits={new Set()}
      doseUnit="µM"
      showConcentration
      selection={EMPTY_SELECTION}
      onRowClick={() => {}}
      {...over}
    />,
  );

const leaves = () => defs.flatMap((c) => c.children ?? [c]);
const column = (colId: string) => leaves().find((c) => c.colId === colId);

beforeEach(() => {
  defs = [];
  drawGrid = false;
});

describe("MeltResultsGrid columns", () => {
  it.each([[["Main"]], [["Low", "Main"]]])("Sample flexes, the rest are fixed (%j)", (names) => {
    show(names);
    for (const c of leaves()) {
      if (c.colId === "sample") {
        expect(c.flex).toBe(1);
        expect(c.minWidth).toBeGreaterThanOrEqual(180);
      } else {
        expect(c.flex).toBeUndefined();
        expect(typeof c.width).toBe("number");
      }
    }
  });

  it("has a Concentration column only when a position of the run has a concentration", () => {
    const headers = () => leaves().map((c) => c.headerName);
    const total = () => leaves().reduce((sum, c) => sum + c.width, 0);
    show(["Main"], { showConcentration: true });
    expect(headers()).toEqual([
      "Sample",
      "Position",
      "Conc. (µM)",
      "Tm (°C)",
      "ΔTm (°C)",
      "Hit",
      "Status",
    ]);
    const withColumn = { sample: column("sample").width, total: total() };

    show(["Main"], { showConcentration: false });
    expect(headers()).toEqual(["Sample", "Position", "Tm (°C)", "ΔTm (°C)", "Hit", "Status"]);
    // The grid shares its width in proportion to these widths: the hidden
    // column's goes to Sample, so the other columns stay as wide as they were.
    expect(column("sample").width).toBeGreaterThan(withColumn.sample);
    expect(total()).toBe(withColumn.total);
  });

  it("keeps the full sample text in a title, with the unregistered tag", () => {
    show(["Main"]);
    const sample = defs.find((c) => c.colId === "sample");
    render(sample.cellRenderer({ data: row }));
    expect(screen.getByTitle("Long sample (unregistered)")).toHaveTextContent(/^Long sample$/);
  });
});

describe("MeltResultsGrid values beside a limit of the hit rule", () => {
  // ΔTm −2.02 under "outside −2 to 2" is a hit; Tm 59.96 under "< 60" is one too.
  const near = {
    ...row,
    cells: { Main: { tm: 59.96, deltaTm: -2.02, namedBy: "range", outsidePeaks: [] } },
  } as unknown as ResultRow;
  const applicable = [
    {
      rule: { readout_name: "ΔTm (Main)", operator: "not_between", value: [-2, 2] },
      window: "Main",
      measure: "delta_tm",
    },
    {
      rule: { readout_name: "Tm (Main)", operator: "lt", value: 60 },
      window: "Main",
      measure: "tm",
    },
  ] as ApplicableRule[];

  it("shows two decimals, so the side of the limit can be read", () => {
    show(["Main"], { applicable });
    expect(column("Main:delta").valueFormatter({ data: near, value: -2.02 })).toBe("−2.02");
    expect(column("Main:tm").cellRenderer({ data: near })).toBe("59.96");
    expect(column("Main:tm").valueFormatter({ data: near, value: 59.96 })).toBe("59.96");
    // A value clear of the limits keeps one decimal.
    expect(column("Main:delta").valueFormatter({ data: near, value: -2.4 })).toBe("−2.4");
  });

  it("shows one decimal without a rule on that window and measure", () => {
    show(["Main"], { applicable: [{ ...applicable[0], window: "Low" }] });
    expect(column("Main:delta").valueFormatter({ data: near, value: -2.02 })).toBe("−2.0");
    expect(column("Main:tm").cellRenderer({ data: near })).toBe("60.0");
  });
});

describe("MeltResultsGrid with structures", () => {
  const registered = {
    ...row,
    wellId: "w2",
    identity: { ...row.identity, registrationNumber: "CC-1", smiles: "CCO" },
  } as ResultRow;
  const rows = { pinned: [], body: [row, registered] };
  const reviewed = { status: "reviewed", review: "reviewed", differs: false, outsidePeaks: [] };
  /** What a column draws in a row's cell (the grid provides the tooltips' context). */
  const cellOf = (colId: string, data: ResultRow) =>
    render(<TooltipProvider>{column(colId).cellRenderer({ data })}</TooltipProvider>).container
      .firstElementChild as HTMLElement;

  it("lets the Sample column size the rows only while structures are shown", () => {
    show(["Main"], { rows });
    expect(column("sample").autoHeight).toBeFalsy();
    const plain = height;
    show(["Main"], { rows, showStructures: true });
    expect(column("sample").autoHeight).toBe(true);
    // The grid makes room for the one row that carries a structure: 100 px, not the usual 36.
    expect(height).toBe(plain - 36 + 100);
    // Rows without a structure add nothing.
    show(["Main"], { rows: { pinned: [], body: [row, row] }, showStructures: true });
    expect(height).toBe(plain);
  });

  it("draws the structure in the Sample cell of the row that has one", async () => {
    drawGrid = true;
    show(["Main"], { rows, showStructures: true });
    const drawing = await screen.findByTestId("structure");
    expect(drawing.closest('[col-id="sample"]')).toHaveTextContent("CC-1");
    expect(screen.getAllByTestId("structure")).toHaveLength(1);
  });

  it("puts the structure, 72 px high, directly under the Sample text line", () => {
    show(["Main"], { rows, showStructures: true });
    const [line, drawing, ...rest] = cellOf("sample", registered).children;
    expect(rest).toHaveLength(0);
    // The text takes one line of the cell, where the other cells' values are.
    expect(line).toHaveTextContent(/^CC-1$/);
    expect(line).toHaveClass("h-[1lh]");
    // The drawing is the line's sibling: no wrapper pads it into a band.
    expect(drawing).toHaveAttribute("data-testid", "structure");
    expect(drawing).toHaveAttribute("data-height", "72");
    // Wider than tall, as most structures are drawn, so the drawing fills its box.
    expect(drawing).toHaveAttribute("data-width", "144");
  });

  it("a row without a structure keeps its text centered on a line as tall as the row", () => {
    show(["Main"], { rows, showStructures: true });
    const [line, ...rest] = cellOf("sample", row).children;
    expect(rest).toHaveLength(0);
    expect(line).toHaveClass("h-[34px]", "leading-[34px]");
  });

  it("aligns the Status chip of a row with a structure to the top line, as its other cells", () => {
    const tall = { ...registered, cells: { Main: reviewed } } as unknown as ResultRow;
    const normal = { ...row, cells: { Main: reviewed } } as unknown as ResultRow;
    show(["Main"], { rows, showStructures: true });
    expect(cellOf("status", tall)).toHaveTextContent(/^Reviewed$/);
    expect(cellOf("status", tall)).toHaveClass("h-[1lh]", "items-center");
    expect(cellOf("status", tall)).not.toHaveClass("h-full");
    // A row of the normal height keeps its chip centered in the row.
    expect(cellOf("status", normal)).toHaveClass("h-full", "items-center");
    // So does every row while structures are not shown.
    show(["Main"], { rows });
    expect(cellOf("status", tall)).toHaveClass("h-full", "items-center");
    // Position and ΔTm are plain values, and a Tm is too: nothing takes them off that line.
    expect(column("position").cellRenderer).toBeUndefined();
    expect(column("Main:delta").cellRenderer).toBeUndefined();
    const withTm = { ...tall, cells: { Main: { ...reviewed, tm: 57.1, namedBy: "range" } } };
    expect(column("Main:tm").cellRenderer({ data: withTm })).toBe("57.1");
  });
});

describe("MeltResultsGrid sorted by Position", () => {
  const numbers = (n: number) => Array.from({ length: n }, (_, i) => i + 1);
  const at = (position: string, holderRank: number, over: Partial<ResultRow> = {}) =>
    ({ ...row, wellId: position, position, holderRank, ...over }) as ResultRow;
  const asText = (a: ResultRow, b: ResultRow) => a.position.localeCompare(b.position);
  const shown = (container: string) =>
    [...document.querySelectorAll<HTMLElement>(`${container} [role="row"]`)]
      .sort((a, b) => Number(a.getAttribute("row-index")) - Number(b.getAttribute("row-index")))
      .map((r) => r.querySelector('[col-id="position"]')?.textContent);
  const body = () => shown(".ag-center-cols-container");
  const sortByPosition = () => fireEvent.click(screen.getByText("Position"));

  // The holder's order, both ways, with the rows given as text sorts them.
  it.each([
    ["a cassette of 24", numbers(24).map((n) => `Capillary ${n}`)],
    ["a plate", ["A", "B"].flatMap((r) => numbers(12).map((n) => `${r}${n}`))],
  ])("orders %s as the holder is laid out, in both directions", async (_, labels) => {
    drawGrid = true;
    const [first, ...rest] = labels.map((label, i) => at(label, i));
    // The first position is the reference: pinned, so never sorted.
    const pinned = [{ ...first, wellType: "reference", isSample: false } as ResultRow];
    show(["Main"], { rows: { pinned, body: rest.sort(asText) } });
    await screen.findByText(labels[1]);

    sortByPosition();
    await waitFor(() => expect(body()).toEqual(labels.slice(1)));
    expect(shown(".ag-floating-top")).toEqual([labels[0]]);
    sortByPosition();
    await waitFor(() => expect(body()).toEqual(labels.slice(1).reverse()));
    expect(shown(".ag-floating-top")).toEqual([labels[0]]);
  });
});

describe("MeltResultsGrid without sample rows", () => {
  it("draws no empty-grid notice over the pinned reference row", async () => {
    drawGrid = true;
    const reference = {
      ...row,
      wellId: "w0",
      wellType: "reference",
      isSample: false,
      sampleText: "Protein alone",
      identity: { ...row.identity, label: "Protein alone" },
    } as ResultRow;
    show(["Main"], { rows: { pinned: [reference], body: [] } });
    expect(await screen.findByText("Protein alone")).toBeInTheDocument();
    expect(screen.queryByText("No Rows To Show")).not.toBeInTheDocument();
  });
});
