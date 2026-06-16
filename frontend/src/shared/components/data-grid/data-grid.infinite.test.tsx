import { render } from "@testing-library/react";
import type { IDatasource } from "ag-grid-community";
import { describe, expect, it, vi } from "vitest";
import { DataGrid } from "./data-grid";

// AG Grid is heavy; assert the prop wiring via a mock of AgGridReact.
vi.mock("ag-grid-react", () => ({
  AgGridReact: (props: Record<string, unknown>) => {
    // expose the resolved props for assertions
    (globalThis as Record<string, unknown>).__agProps = props;
    return null;
  },
}));

describe("DataGrid datasource (infinite row model)", () => {
  it("enables infinite model + passes datasource, omits rowData", () => {
    const datasource: IDatasource = { getRows: vi.fn() };
    render(
      <DataGrid
        columnDefs={[{ field: "x" } as never]}
        rowData={undefined}
        datasource={datasource}
      />,
    );
    const p = (globalThis as Record<string, unknown>).__agProps as Record<string, unknown>;
    expect(p.rowModelType).toBe("infinite");
    expect(p.datasource).toBe(datasource);
    expect(p.rowData).toBeUndefined();
  });

  it("stays client-side when no datasource", () => {
    render(<DataGrid columnDefs={[{ field: "x" } as never]} rowData={[{ x: 1 }]} />);
    const p = (globalThis as Record<string, unknown>).__agProps as Record<string, unknown>;
    expect(p.rowModelType).toBeUndefined();
    expect(p.rowData).toEqual([{ x: 1 }]);
  });
});
