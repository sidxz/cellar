import { describe, expect, it, vi } from "vitest";

// Capture Plot props instead of rendering the real Plotly DOM — we're
// asserting on the trace + layout shape the component emits, not the
// pixel output.
const plotCalls: Array<Record<string, unknown>> = [];
vi.mock("@/shared/lib/plotly", () => ({
  Plot: (props: Record<string, unknown>) => {
    plotCalls.push(props);
    return null;
  },
}));

// Stub the chart-color module so the test doesn't depend on the real
// design-token resolution; only the trace mode + layout shapes matter.
vi.mock("@/shared/lib/chart-colors", () => ({
  CHART_AXIS: { tick: "#000", label: "#000" },
  CHART_COLORS: { warning: "#f59e0b" },
  CURVE_DEFAULT_COLOR: "#000",
  CURVE_QUALITY_COLORS: { inactive: "#999", full: "#000" } as Record<string, string>,
}));

import { render } from "@testing-library/react";
import { DoseResponseFigure } from "./dose-response-figure";

function reset() {
  plotCalls.length = 0;
}

const RAW_POINTS = [
  { x: 0.1, y: 5 },
  { x: 1, y: 10 },
  { x: 10, y: 50 },
  { x: 100, y: 95 },
];

interface Trace {
  mode?: string;
  name?: string;
}

describe("<DoseResponseFigure /> — inactive class draws points only", () => {
  it("omits the fit line trace when curve_class is 'inactive'", () => {
    reset();
    render(
      <DoseResponseFigure
        curve={{
          fitted_value: 0.013,
          top: 100,
          bottom: 0,
          hill_slope: -1.29,
          r_squared: 0,
          curve_class: "inactive",
          raw_data: RAW_POINTS,
        }}
        size="sparkline"
      />,
    );
    expect(plotCalls).toHaveLength(1);
    const traces = plotCalls[0].data as Trace[];
    expect(traces.some((t) => t.mode === "lines" && t.name === "Fit")).toBe(false);
    expect(traces.some((t) => t.mode === "markers" && t.name === "Data")).toBe(true);
  });

  it("omits the vertical dashed line at fitted_value when inactive", () => {
    reset();
    render(
      <DoseResponseFigure
        curve={{
          fitted_value: 0.013,
          top: 100,
          bottom: 0,
          hill_slope: -1.29,
          r_squared: 0,
          curve_class: "inactive",
          raw_data: RAW_POINTS,
        }}
        size="sparkline"
      />,
    );
    const layout = plotCalls[0].layout as { shapes?: unknown[] };
    expect(layout.shapes ?? []).toEqual([]);
  });

  it("keeps the fit line + vertical dash for non-inactive curves", () => {
    reset();
    render(
      <DoseResponseFigure
        curve={{
          fitted_value: 5,
          top: 100,
          bottom: 0,
          hill_slope: -1.0,
          r_squared: 0.95,
          curve_class: "full",
          raw_data: RAW_POINTS,
        }}
        size="sparkline"
      />,
    );
    const traces = plotCalls[0].data as Trace[];
    expect(traces.some((t) => t.mode === "lines" && t.name === "Fit")).toBe(true);
    const layout = plotCalls[0].layout as { shapes?: unknown[] };
    expect((layout.shapes ?? []).length).toBeGreaterThan(0);
  });
});
