import { describe, expect, it, vi } from "vitest";

// Capture Plot props rather than render Plotly — we're asserting on the
// trace + shape shapes the chart emits in aggregate mode, not the
// pixel-level rendering (already covered by the figure tests).
const plotCalls: Array<Record<string, unknown>> = [];
vi.mock("@/shared/lib/plotly", () => ({
  Plot: (props: Record<string, unknown>) => {
    plotCalls.push(props);
    return null;
  },
  getPlotlyGlobal: () => null,
}));

vi.mock("@/shared/lib/chart-colors", () => ({
  CHART_AXIS: { tick: "#000", label: "#000", grid: "#ccc" },
  CHART_COLORS: { warning: "#f59e0b", error: "#dc2626", success: "#16a34a" },
  GROUP_PALETTE: ["#000", "#111", "#222", "#333", "#444", "#555", "#666", "#777"],
  CURVE_DEFAULT_COLOR: "#000",
  CURVE_QUALITY_COLORS: { inactive: "#999", full: "#000", partial: "#aaa" } as Record<
    string,
    string
  >,
}));

// Hooks talk to the API — stub to no-op so the chart's edit-mode wiring
// doesn't try to call real endpoints.
vi.mock("../hooks/use-refit-dose-response", () => ({
  useRefitDoseResponse: () => ({ mutate: vi.fn(), isPending: false }),
  useClassifyDoseResponse: () => ({ mutate: vi.fn(), isPending: false }),
}));

import { render } from "@testing-library/react";
import { DoseResponseChart } from "./dose-response-chart";
import type { DoseResponseCurve } from "../types";

function reset() {
  plotCalls.length = 0;
}

const PLACEHOLDER = "00000000-0000-0000-0000-000000000000";

function makeCurve(overrides: Partial<DoseResponseCurve> = {}): DoseResponseCurve {
  return {
    id: PLACEHOLDER,
    workspace_id: PLACEHOLDER,
    molecule_id: PLACEHOLDER,
    registration_number: "CV-00001",
    molecule_name: null,
    synonyms: [],
    smiles: null,
    batch_id: PLACEHOLDER,
    batch_number: null,
    protocol_id: PLACEHOLDER,
    run_id: PLACEHOLDER,
    readout_definition_id: PLACEHOLDER,
    curve_type: "ic50",
    fitted_value: 0.2,
    fitted_unit: "uM",
    hill_slope: -1.0,
    top: 100,
    bottom: 0,
    r_squared: 0.97,
    confidence_interval_low: null,
    confidence_interval_high: null,
    num_points: 4,
    curve_class: "full",
    raw_data: [
      { x: 0.01, y: 5 },
      { x: 0.1, y: 30 },
      { x: 1, y: 80 },
      { x: 10, y: 95 },
    ],
    excluded_points: null,
    fit_quality_warnings: [],
    intercept_values: [],
    ...overrides,
  };
}

interface Trace {
  mode?: string;
  name?: string;
  opacity?: number;
  line?: { dash?: string; width?: number; color?: string };
}

interface ShapeRecord {
  type: string;
  x0: number;
  x1: number;
  line?: { color?: string; width?: number; dash?: string };
  opacity?: number;
}

describe("<DoseResponseChart /> — aggregate-mode overlay", () => {
  it("renders unchanged when additional_curves + aggregate are absent (LATEST behavior)", () => {
    reset();
    render(<DoseResponseChart curves={[makeCurve()]} />);

    const traces = plotCalls[0].data as Trace[];
    // Exactly one fit line — no muted contributing-run overlays.
    const fitLines = traces.filter(
      (t) => t.mode === "lines" && (t.opacity ?? 1) < 1,
    );
    expect(fitLines).toHaveLength(0);
    // The fitted-value cross-hair vertical line is present (showCrossHair
    // defaults to true).
    const layout = plotCalls[0].layout as { shapes?: ShapeRecord[] };
    const vertLines = (layout.shapes ?? []).filter(
      (s) => s.type === "line" && s.x0 === s.x1,
    );
    expect(vertLines.length).toBeGreaterThan(0);
  });

  it("aggregate snapshot adds one muted dashed fit trace per active additional curve", () => {
    reset();
    render(
      <DoseResponseChart
        curves={[
          makeCurve({
            additional_curves: [
              {
                fitted_value: 0.4,
                top: 100,
                bottom: 0,
                hill_slope: -1,
                curve_class: "full",
                run_date: "2026-03-01",
                run_id: "11111111-1111-1111-1111-111111111111",
              },
              {
                fitted_value: 0.1,
                top: 100,
                bottom: 0,
                hill_slope: -1,
                curve_class: "full",
                run_date: "2026-01-01",
                run_id: "22222222-2222-2222-2222-222222222222",
              },
            ],
            aggregate: { marker_x: 0.2, marker_label: "gmean", unit: "uM" },
          }),
        ]}
      />,
    );

    const traces = plotCalls[0].data as Trace[];
    const overlays = traces.filter(
      (t) =>
        t.mode === "lines" &&
        t.line?.dash === "dot" &&
        (t.opacity ?? 1) < 1 &&
        (t.name?.startsWith("Run ") ?? false),
    );
    expect(overlays).toHaveLength(2);
  });

  it("skips inactive contributors in the overlay", () => {
    reset();
    render(
      <DoseResponseChart
        curves={[
          makeCurve({
            additional_curves: [
              {
                fitted_value: 0.4,
                top: 100,
                bottom: 0,
                hill_slope: -1,
                curve_class: "full",
                run_date: "2026-03-01",
                run_id: "11111111-1111-1111-1111-111111111111",
              },
              {
                fitted_value: 0.5,
                top: 100,
                bottom: 0,
                hill_slope: -1,
                curve_class: "inactive",
                run_date: "2026-02-01",
                run_id: "22222222-2222-2222-2222-222222222222",
              },
            ],
            aggregate: { marker_x: 0.2, marker_label: "gmean", unit: "uM" },
          }),
        ]}
      />,
    );

    const traces = plotCalls[0].data as Trace[];
    const overlays = traces.filter(
      (t) =>
        t.mode === "lines" &&
        t.line?.dash === "dot" &&
        (t.opacity ?? 1) < 1 &&
        (t.name?.startsWith("Run ") ?? false),
    );
    expect(overlays).toHaveLength(1);
  });

  it("replaces per-curve cross-hair with a single solid amber marker at marker_x", () => {
    reset();
    render(
      <DoseResponseChart
        curves={[
          makeCurve({
            additional_curves: [],
            aggregate: { marker_x: 0.15, marker_label: "gmean", unit: "uM" },
          }),
        ]}
      />,
    );

    const layout = plotCalls[0].layout as { shapes?: ShapeRecord[] };
    const verticalShapes = (layout.shapes ?? []).filter(
      (s) => s.type === "line" && s.x0 === s.x1,
    );
    // There should be exactly one vertical line, sitting at marker_x — NOT
    // at the rep curve's fitted_value (which is 0.2 in makeCurve()).
    expect(verticalShapes).toHaveLength(1);
    expect(verticalShapes[0].x0).toBe(0.15);
    // Solid (no dash) and amber — distinct from the dotted per-curve dash
    // that LATEST cells draw.
    expect(verticalShapes[0].line?.dash).toBeUndefined();
    expect(verticalShapes[0].line?.color).toBe("#f59e0b");
  });

  it("suppresses additional-intercept dashed lines in aggregate mode", () => {
    reset();
    render(
      <DoseResponseChart
        curves={[
          makeCurve({
            // Multi-intercept curve (EC50 + EC90 on the same Hill fit).
            intercept_values: [
              {
                spec: {
                  kind: "ec",
                  level: 50,
                  basis: "relative_percent",
                  label: "EC50",
                },
                value: 0.2,
                confidence_interval_low: null,
                confidence_interval_high: null,
                at_bound: false,
              },
              {
                spec: {
                  kind: "ec",
                  level: 90,
                  basis: "relative_percent",
                  label: "EC90",
                },
                value: 1.5,
                confidence_interval_low: null,
                confidence_interval_high: null,
                at_bound: false,
              },
            ],
            aggregate: { marker_x: 0.18, marker_label: "gmean", unit: "uM" },
          }),
        ]}
      />,
    );

    const layout = plotCalls[0].layout as { shapes?: ShapeRecord[] };
    // longdash is the per-intercept dash style — should be absent in
    // aggregate mode since per-curve intercepts don't equal the cell value.
    const longdash = (layout.shapes ?? []).filter(
      (s) => s.line?.dash === "longdash",
    );
    expect(longdash).toHaveLength(0);
  });
});
