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

interface OverlayTrace extends Trace {
  opacity?: number;
  line?: { dash?: string; width?: number; color?: string };
  showlegend?: boolean;
}

interface ShapeRecord {
  type: string;
  x0: number;
  x1: number;
  line?: { color?: string; width?: number; dash?: string };
}

describe("<DoseResponseFigure /> — aggregate-mode overlay", () => {
  const baseCurve = {
    fitted_value: 5,
    top: 100,
    bottom: 0,
    hill_slope: -1.0,
    r_squared: 0.95,
    curve_class: "full",
    raw_data: RAW_POINTS,
  };

  it("renders unchanged when additional_curves and aggregate are absent (LATEST behavior)", () => {
    reset();
    render(<DoseResponseFigure curve={baseCurve} size="sparkline" />);
    const traces = plotCalls[0].data as OverlayTrace[];
    // Exactly one fit line; no muted overlays.
    const fitLines = traces.filter((t) => t.mode === "lines");
    expect(fitLines).toHaveLength(1);
    expect(fitLines[0].name).toBe("Fit");
    expect(fitLines[0].opacity ?? 1).toBe(1);
    // Exactly one vertical-dashed line at fitted_value.
    const layout = plotCalls[0].layout as { shapes?: ShapeRecord[] };
    expect(layout.shapes).toHaveLength(1);
    expect(layout.shapes![0].x0).toBe(baseCurve.fitted_value);
    expect(layout.shapes![0].line?.dash).toBe("dot");
  });

  it("aggregate snapshot adds one muted dashed fit trace per active additional curve", () => {
    reset();
    render(
      <DoseResponseFigure
        curve={{
          ...baseCurve,
          additional_curves: [
            {
              fitted_value: 2.0,
              top: 100,
              bottom: 0,
              hill_slope: -1,
              curve_class: "full",
              run_date: "2026-03-01",
              run_id: "r1",
            },
            {
              fitted_value: 8.0,
              top: 100,
              bottom: 0,
              hill_slope: -1,
              curve_class: "full",
              run_date: "2026-01-01",
              run_id: "r2",
            },
          ],
          aggregate: { marker_x: 5.0, marker_label: "mean", unit: "uM" },
        }}
        size="sparkline"
      />,
    );
    const traces = plotCalls[0].data as OverlayTrace[];
    // 1 primary fit (full opacity) + 2 muted overlays (dashed, ~0.35).
    const fitLines = traces.filter((t) => t.mode === "lines");
    expect(fitLines).toHaveLength(3);
    const overlays = fitLines.filter((t) => (t.opacity ?? 1) < 1);
    expect(overlays).toHaveLength(2);
    for (const o of overlays) {
      expect(o.opacity).toBeCloseTo(0.35);
      expect(o.line?.dash).toBe("dot");
      expect(o.showlegend).toBe(false);
    }
    // The non-overlay fit line is the primary (full opacity, no dash).
    const primary = fitLines.find((t) => (t.opacity ?? 1) === 1);
    expect(primary).toBeDefined();
    expect(primary!.line?.dash).toBeUndefined();
  });

  it("aggregate snapshot draws ONE solid vertical line at aggregate.marker_x (no per-curve dash)", () => {
    reset();
    render(
      <DoseResponseFigure
        curve={{
          ...baseCurve,
          additional_curves: [
            {
              fitted_value: 2.0,
              top: 100,
              bottom: 0,
              hill_slope: -1,
              curve_class: "full",
              run_date: "2026-03-01",
              run_id: "r1",
            },
          ],
          aggregate: { marker_x: 3.7, marker_label: "mean", unit: "uM" },
        }}
        size="sparkline"
      />,
    );
    const layout = plotCalls[0].layout as { shapes?: ShapeRecord[] };
    expect(layout.shapes).toHaveLength(1);
    const marker = layout.shapes![0];
    expect(marker.x0).toBe(3.7);
    expect(marker.x1).toBe(3.7);
    // Solid (no dash) and thicker than the per-curve dashed line.
    expect(marker.line?.dash).toBeUndefined();
    expect(marker.line?.width).toBeGreaterThanOrEqual(1.5);
  });

  it("inactive additional curves are skipped in the overlay; aggregate marker still draws", () => {
    reset();
    render(
      <DoseResponseFigure
        curve={{
          ...baseCurve,
          additional_curves: [
            {
              fitted_value: 2.0,
              top: 100,
              bottom: 0,
              hill_slope: -1,
              curve_class: "inactive",
              run_date: "2026-03-01",
              run_id: "r1",
            },
            {
              fitted_value: 8.0,
              top: 100,
              bottom: 0,
              hill_slope: -1,
              curve_class: "inactive",
              run_date: "2026-01-01",
              run_id: "r2",
            },
          ],
          aggregate: { marker_x: 5.0, marker_label: "mean", unit: "uM" },
        }}
        size="sparkline"
      />,
    );
    const traces = plotCalls[0].data as OverlayTrace[];
    // Only the primary fit line — both inactive additionals are skipped.
    const fitLines = traces.filter((t) => t.mode === "lines");
    expect(fitLines).toHaveLength(1);
    expect(fitLines[0].opacity ?? 1).toBe(1);
    // Marker still draws.
    const layout = plotCalls[0].layout as { shapes?: ShapeRecord[] };
    expect(layout.shapes).toHaveLength(1);
    expect(layout.shapes![0].x0).toBe(5.0);
  });

  it("computeXRange folds in additional curves' fitted_values so overlays aren't truncated", () => {
    reset();
    render(
      <DoseResponseFigure
        curve={{
          ...baseCurve,
          // raw_data spans 0.1..100; sibling EC50 at 1000 should extend
          // the axis ceiling so the overlay fit doesn't run off-chart.
          additional_curves: [
            {
              fitted_value: 1000,
              top: 100,
              bottom: 0,
              hill_slope: -1,
              curve_class: "full",
              run_date: "2026-03-01",
              run_id: "r1",
            },
          ],
          aggregate: { marker_x: 50, marker_label: "mean", unit: "uM" },
        }}
        size="sparkline"
      />,
    );
    const layout = plotCalls[0].layout as {
      xaxis?: { range?: number[] };
    };
    // x-axis range is log10. The right edge should sit past log10(1000)=3,
    // proving the sibling's fitted_value was included in xs.
    expect(layout.xaxis?.range).toBeDefined();
    const [, hi] = layout.xaxis!.range!;
    expect(hi).toBeGreaterThanOrEqual(3);
  });
});
