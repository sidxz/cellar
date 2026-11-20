import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import type { ColDef, ColGroupDef } from "ag-grid-community";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { PivotRow } from "../lib/readout-data-pivot";
import { ReadoutDataTable } from "./readout-data-table";

afterEach(cleanup);

// Renders each row's raw readout cells as the grid would, without AG Grid.
vi.mock("@/shared/components/data-grid/data-grid", () => ({
  DataGrid: ({
    rowData,
    columnDefs,
  }: { rowData: PivotRow[]; columnDefs: (ColDef<PivotRow> | ColGroupDef<PivotRow>)[] }) => (
    <ul>
      {rowData.map((row) => (
        <li key={row.key} data-testid={row.registrationNumber}>
          {columnDefs
            .flatMap((column) =>
              "children" in column ? (column.children as ColDef<PivotRow>[]) : [column],
            )
            .filter((c) => c.colId?.endsWith("::raw"))
            .map((c) => (
              <span key={c.colId}>
                {(c.cellRenderer as (p: { data: PivotRow }) => ReactNode)({ data: row })}
              </span>
            ))}
        </li>
      ))}
    </ul>
  ),
}));

const readout = (molecule: string, overrides: Record<string, unknown>) => ({
  id: `rd-${molecule}`,
  molecule_id: molecule,
  batch_id: `b-${molecule}`,
  registration_number: molecule,
  readout_definition_id: "rd-1",
  is_computed: false,
  value_numeric: 1.5,
  value_qualifier: "=",
  well_id: null,
  ...overrides,
});

// A test may swap in its own rows to stand in for a refetch.
const readoutRows = vi.hoisted(() => ({ current: null as unknown[] | null }));
afterEach(() => {
  readoutRows.current = null;
});

vi.mock("../hooks/use-readout-data", () => ({
  useReadoutDataByRun: () => ({
    data: readoutRows.current ?? [
      readout("CPD-1", { replicate_count: 3 }),
      readout("CPD-2", { replicate_count: null }),
      readout("CPD-3", { well_id: "w-1", replicate_count: 2 }),
    ],
    isLoading: false,
  }),
}));
vi.mock("../hooks/use-dose-response", () => ({ useDoseResponseByRun: () => ({ data: [] }) }));
vi.mock("../hooks/use-plate-setup", () => ({ usePlateMap: () => ({ data: undefined }) }));
vi.mock("../hooks/use-protocols", () => ({
  useProtocol: () => ({
    data: {
      readout_definitions: [
        { id: "rd-1", name: "IC50", unit: "µM", data_type: "numeric", is_calculated: false },
      ],
    },
  }),
}));

describe("ReadoutDataTable replicate count", () => {
  it("shows n on summary rows, a quiet dash when not recorded, and nothing on well rows", () => {
    render(<ReadoutDataTable runId="run-1" protocolId="proto-1" />);

    expect(within(screen.getByTestId("CPD-1")).getByText("n=3")).toHaveAttribute(
      "title",
      "Mean of 3 replicates",
    );
    expect(within(screen.getByTestId("CPD-2")).getByText("n —")).toHaveAttribute(
      "title",
      "Replicates not recorded",
    );
    expect(screen.getByTestId("CPD-3")).toHaveTextContent("1.500");
    expect(screen.getByTestId("CPD-3")).not.toHaveTextContent("n=");
  });

  it("hides and restores a readout through View without removing its compound rows", () => {
    render(<ReadoutDataTable runId="run-1" protocolId="proto-1" />);
    fireEvent.keyDown(screen.getByRole("button", { name: "View" }), { key: "Enter" });
    fireEvent.click(screen.getByRole("menuitemcheckbox", { name: "IC50" }));
    expect(screen.getByTestId("CPD-1")).not.toHaveTextContent("1.500");
    expect(screen.getByTestId("CPD-3")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("menuitemcheckbox", { name: "IC50" }));
    expect(screen.getByTestId("CPD-1")).toHaveTextContent("1.500");
    expect(screen.getByRole("menuitemcheckbox", { name: "Chemical structures" })).toBeVisible();
  });
});

describe("ReadoutDataTable outlier filter", () => {
  it("shows every row again once a refetch clears the last outlier", () => {
    readoutRows.current = [readout("CPD-1", { is_outlier: true }), readout("CPD-2", {})];
    const { rerender } = render(<ReadoutDataTable runId="run-1" protocolId="proto-1" />);
    fireEvent.click(screen.getByRole("button", { name: "Outliers (1)" }));
    expect(screen.queryByTestId("CPD-2")).not.toBeInTheDocument();

    readoutRows.current = [readout("CPD-1", {}), readout("CPD-2", {})];
    rerender(<ReadoutDataTable runId="run-1" protocolId="proto-1" />);
    expect(screen.queryByRole("button", { name: /Outliers/ })).not.toBeInTheDocument();
    expect(screen.getByTestId("CPD-1")).toBeInTheDocument();
    expect(screen.getByTestId("CPD-2")).toBeInTheDocument();
  });
});
