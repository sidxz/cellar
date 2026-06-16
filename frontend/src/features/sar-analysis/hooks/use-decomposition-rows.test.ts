import { renderHook, waitFor } from "@testing-library/react";
import type { IGetRowsParams } from "ag-grid-community";
import { describe, expect, it, vi } from "vitest";
import { useDecompositionRows } from "./use-decomposition-rows";

const PAGE = {
  rows: [
    {
      molecule_id: "m1",
      smiles: "Fc1ccccc1",
      registration_number: "CV-1",
      name: null,
      rgroups: { R1: "F" },
      mw: 96,
      clogp: 1.8,
      tpsa: 0,
      activity: 0.1,
      activity_snapshot: { value: 0.1 },
    },
  ],
  total: 1,
  activity_reference: 0.1,
};

function getRowsParams(over: Partial<IGetRowsParams> = {}): IGetRowsParams {
  return {
    startRow: 0,
    endRow: 100,
    sortModel: [],
    filterModel: {},
    successCallback: vi.fn(),
    failCallback: vi.fn(),
    context: {},
    ...over,
  } as unknown as IGetRowsParams;
}

describe("useDecompositionRows", () => {
  it("builds a datasource whose getRows POSTs /rows and maps server rows", async () => {
    const fetchFn = vi.fn().mockResolvedValue(PAGE);
    const { result } = renderHook(() => useDecompositionRows("run-1", "proj-1", { fetchFn }));
    const ds = result.current.datasource;
    expect(ds).not.toBeNull();
    const params = getRowsParams({ sortModel: [{ colId: "mw", sort: "asc" }] as never });
    await ds?.getRows(params);
    expect(fetchFn).toHaveBeenCalledWith("run-1", {
      offset: 0,
      limit: 100,
      sort: [{ col: "molecular_weight", dir: "asc" }],
      filter: undefined,
      projection_id: "proj-1",
    });
    expect(params.successCallback).toHaveBeenCalledWith(
      [expect.objectContaining({ id: "m1", activity: 0.1 })],
      1,
    );
    await waitFor(() => expect(result.current.activityReference).toBe(0.1));
  });

  it("calls failCallback when the fetch throws", async () => {
    const fetchFn = vi.fn().mockRejectedValue(new Error("boom"));
    const { result } = renderHook(() => useDecompositionRows("run-1", null, { fetchFn }));
    const params = getRowsParams();
    await result.current.datasource?.getRows(params);
    expect(params.failCallback).toHaveBeenCalled();
  });

  it("returns a null datasource without a runId", () => {
    const { result } = renderHook(() => useDecompositionRows(null, null, { fetchFn: vi.fn() }));
    expect(result.current.datasource).toBeNull();
  });

  it("exposes the live filterParam and total after a getRows call", async () => {
    const fetchFn = vi.fn().mockResolvedValue(PAGE);
    const { result } = renderHook(() => useDecompositionRows("run-1", "proj-1", { fetchFn }));
    const params = getRowsParams({
      filterModel: { mw: { filterType: "number", type: "greaterThan", filter: 400 } } as never,
    });
    await result.current.datasource?.getRows(params);
    await waitFor(() => expect(result.current.total).toBe(1));
    expect(result.current.filterParam).toEqual({
      molecular_weight: { kind: "number", op: "gt", value: 400 },
    });
  });

  it("filterParam is undefined when no column filter is active", async () => {
    const fetchFn = vi.fn().mockResolvedValue(PAGE);
    const { result } = renderHook(() => useDecompositionRows("run-1", null, { fetchFn }));
    await result.current.datasource?.getRows(getRowsParams());
    await waitFor(() => expect(result.current.total).toBe(1));
    expect(result.current.filterParam).toBeUndefined();
  });
});
