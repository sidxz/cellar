import { act, render } from "@testing-library/react";
import type { IDatasource } from "ag-grid-community";
import { describe, expect, it, vi } from "vitest";
import { DataGrid } from "./data-grid";

function agProps() {
  return (globalThis as Record<string, unknown>).__agProps as Record<string, unknown>;
}

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

describe("DataGrid cross-block selection (infinite + multi-select)", () => {
  function renderInfiniteSelect(onRows?: (rows: unknown[]) => void) {
    return render(
      <DataGrid
        columnDefs={[{ field: "x" } as never]}
        rowData={undefined}
        datasource={{ getRows: vi.fn() } as IDatasource}
        getRowId={(p) => (p.data as { id: string }).id}
        selectionToolbar={(rows) => {
          onRows?.(rows);
          return null;
        }}
      />,
    );
  }

  it("suppresses the select-all header checkbox in the infinite model", () => {
    renderInfiniteSelect();
    const cols = agProps().columnDefs as Array<Record<string, unknown>>;
    expect(cols[0].colId).toBe("__select__");
    // No select-all-loaded footgun; per-row checkbox stays.
    expect(cols[0].headerCheckboxSelection).toBe(false);
    expect(cols[0].checkboxSelection).toBe(true);
    expect(typeof agProps().onRowSelected).toBe("function");
    expect(typeof agProps().onModelUpdated).toBe("function");
  });

  it("keeps the select-all header in the client model", () => {
    render(
      <DataGrid
        columnDefs={[{ field: "x" } as never]}
        rowData={[{ x: 1 }]}
        selectionToolbar={() => null}
      />,
    );
    const cols = agProps().columnDefs as Array<Record<string, unknown>>;
    expect(cols[0].headerCheckboxSelection).toBe(true);
  });

  it("accumulates picks by id across blocks and drops on deselect", () => {
    const seen: unknown[][] = [];
    renderInfiniteSelect((rows) => seen.push(rows));
    const onRowSelected = agProps().onRowSelected as (e: unknown) => void;
    act(() => {
      onRowSelected({ node: { data: { id: "a" }, isSelected: () => true } });
      onRowSelected({ node: { data: { id: "b" }, isSelected: () => true } });
    });
    expect(seen.at(-1)).toEqual([{ id: "a" }, { id: "b" }]);
    // Deselect 'a' — 'b' survives even though 'a's block could be unloaded.
    act(() => {
      onRowSelected({ node: { data: { id: "a" }, isSelected: () => false } });
    });
    expect(seen.at(-1)).toEqual([{ id: "b" }]);
  });
});
