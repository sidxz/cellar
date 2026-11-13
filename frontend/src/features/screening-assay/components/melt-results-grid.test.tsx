import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { ResultRow } from "../lib/melt-results";

let defs: any[] = [];
vi.mock("@/shared/components/data-grid/data-grid", () => ({
  DataGrid: (p: { columnDefs: any[] }) => {
    defs = p.columnDefs;
    return null;
  },
}));

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

const show = (windowNames: string[]) =>
  render(
    <MeltResultsGrid
      rows={{ pinned: [], body: [row] }}
      windowNames={windowNames}
      threshold={2}
      doseUnit="µM"
      selection={EMPTY_SELECTION}
      onRowClick={() => {}}
    />,
  );

const leaves = () => defs.flatMap((c) => c.children ?? [c]);

beforeEach(() => {
  defs = [];
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

  it("keeps the full sample text in a title", () => {
    show(["Main"]);
    const sample = defs.find((c) => c.colId === "sample");
    render(sample.cellRenderer({ data: row }));
    expect(screen.getByTitle("Long sample")).toBeInTheDocument();
  });
});
