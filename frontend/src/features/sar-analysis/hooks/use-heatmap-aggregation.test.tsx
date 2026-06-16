import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";
import { useHeatmapAggregation } from "./use-heatmap-aggregation";

function wrap() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
}

const HEATMAP = {
  x_values: ["Cl"],
  y_values: ["F"],
  cells: [
    {
      y: "F",
      x: "Cl",
      count: 2,
      best_scalar: 0.1,
      best_molecule_id: "m1",
      best_molecule_label: "CV-1",
      best_snapshot: {},
    },
  ],
  y_total: 1,
  x_total: 1,
  truncated: false,
};

describe("useHeatmapAggregation", () => {
  it("fetches server cells when run + projection + axes set", async () => {
    const fetchFn = vi.fn().mockResolvedValue(HEATMAP);
    const { result } = renderHook(
      () =>
        useHeatmapAggregation({
          runId: "run-1",
          projectionId: "proj-1",
          axisY: "R1",
          axisX: "R2",
          fetchFn,
        }),
      { wrapper: wrap() },
    );
    await waitFor(() => expect(result.current.data).not.toBeNull());
    expect(result.current.data?.cells[0].best_scalar).toBe(0.1);
    expect(fetchFn).toHaveBeenCalledWith("run-1", {
      axis_y: "R1",
      axis_x: "R2",
      projection_id: "proj-1",
    });
  });

  it("is disabled until run + projection + both axes are present", () => {
    const fetchFn = vi.fn();
    renderHook(
      () =>
        useHeatmapAggregation({
          runId: "run-1",
          projectionId: null,
          axisY: "R1",
          axisX: "R2",
          fetchFn,
        }),
      { wrapper: wrap() },
    );
    expect(fetchFn).not.toHaveBeenCalled();
  });
});
