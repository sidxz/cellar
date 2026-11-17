import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { ApplicableRule } from "../lib/melt-hits";
import type { ResultRow } from "../lib/melt-results";

let defs: any[] = [];
/** Draw the grid itself, not only capture its columns. */
let drawGrid = false;
vi.mock("@/shared/components/data-grid/data-grid", async (importOriginal) => {
  const { DataGrid } =
    await importOriginal<typeof import("@/shared/components/data-grid/data-grid")>();
  return {
    DataGrid: (p: { columnDefs: any[]; rowData: unknown[] }) => {
      defs = p.columnDefs;
      return drawGrid ? <DataGrid {...p} /> : null;
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
