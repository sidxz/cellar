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

// Auth hook is only used for the editor's authorId. Tests don't need a real
// session; an empty string flows through without breaking the local draft state.
vi.mock("@sentinel-auth/nextjs", () => ({
  useAuthz: () => ({ user: { userId: "test-user" } }),
}));

// The orval-generated commit-refit call is hit by the React Query mutation
// when the save dialog is submitted. Stub to avoid network.
vi.mock("@/shared/lib/api/readout-data/readout-data", () => ({
  refitDoseResponseCurveApiV1DoseResponseCurvesCurveIdRefitPost: vi.fn(
    async () => ({}),
  ),
  refitDoseResponseCurvePreviewApiV1DoseResponseCurvesCurveIdRefitPreviewPost: vi.fn(
    async () => ({
      fitted_value: 1.0,
      hill_slope: -1,
      top: 100,
      bottom: 0,
      r_squared: 0.95,
      curve_class: "full",
      points_in_fit: 4,
      points_total: 4,
    }),
  ),
}));

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, fireEvent } from "@testing-library/react";
import { DoseResponseChart } from "./dose-response-chart";
import type { DoseResponseCurve } from "../types";

// React Query wrapper — the chart hosts a useMutation for the commit refit.
function renderWithQuery(ui: React.ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>{ui}</QueryClientProvider>,
  );
}

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
    renderWithQuery(<DoseResponseChart curves={[makeCurve()]} />);

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
    renderWithQuery(
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
    renderWithQuery(
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
    renderWithQuery(
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
    renderWithQuery(
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

describe("<DoseResponseChart /> — point counter", () => {
  it("counter reflects server-excluded points even with empty local draft", () => {
    reset();
    const curve = makeCurve({
      raw_data: Array(8).fill({ x: 1, y: 0 }),
      excluded_points: [{ idx: 5 }, { idx: 7 }],
    });
    renderWithQuery(<DoseResponseChart curves={[curve]} />);
    expect(screen.getByText(/8 of 10 points in fit/i)).toBeInTheDocument();
    expect(screen.getByText(/2 excluded/i)).toBeInTheDocument();
  });

  it("counter shows full denominator when no points are excluded", () => {
    reset();
    const curve = makeCurve({
      raw_data: Array(10).fill({ x: 1, y: 0 }),
      excluded_points: [],
    });
    renderWithQuery(<DoseResponseChart curves={[curve]} />);
    expect(screen.getByText(/10 of 10 points in fit/i)).toBeInTheDocument();
    // No exclusions → no "N excluded" sub-line.
    expect(screen.queryByText(/excluded/i)).not.toBeInTheDocument();
  });
});

describe("<DoseResponseChart /> — edit-session integration", () => {
  it("Edit Points opens a session with side panel and banner", () => {
    reset();
    renderWithQuery(
      <DoseResponseChart curves={[makeCurve()]} isInteractive />,
    );

    fireEvent.click(screen.getByRole("button", { name: /edit points/i }));
    // Banner appears with the unsaved-count.
    expect(
      screen.getByText(/editing — 0 unsaved changes/i),
    ).toBeInTheDocument();
    // Save button starts disabled (no draft changes yet).
    expect(
      screen.getByRole("button", { name: /^save$/i }),
    ).toBeDisabled();
    // Inventory side panel renders — it carries an aria-label on the wrapper.
    expect(screen.getByLabelText(/point inventory/i)).toBeInTheDocument();
  });

  it("toggling a point in the inventory updates the banner count", () => {
    reset();
    renderWithQuery(
      <DoseResponseChart curves={[makeCurve()]} isInteractive />,
    );
    fireEvent.click(screen.getByRole("button", { name: /edit points/i }));

    // Click the first data row in the inventory (row 0 is the header).
    const rows = screen.getAllByRole("row");
    fireEvent.click(rows[1]);

    expect(
      screen.getByText(/editing — 1 unsaved change(?!s)/i),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /save 1/i }),
    ).toBeEnabled();
  });

  it("Cancel with no draft exits cleanly", () => {
    reset();
    renderWithQuery(
      <DoseResponseChart curves={[makeCurve()]} isInteractive />,
    );
    fireEvent.click(screen.getByRole("button", { name: /edit points/i }));
    fireEvent.click(screen.getByRole("button", { name: /cancel/i }));
    expect(screen.queryByText(/editing/i)).not.toBeInTheDocument();
    // Edit Points button is back.
    expect(
      screen.getByRole("button", { name: /edit points/i }),
    ).toBeInTheDocument();
  });

  it("Cancel with dirty draft confirms before exit (window.confirm = no)", () => {
    reset();
    const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(false);
    renderWithQuery(
      <DoseResponseChart curves={[makeCurve()]} isInteractive />,
    );
    fireEvent.click(screen.getByRole("button", { name: /edit points/i }));
    fireEvent.click(screen.getAllByRole("row")[1]);
    fireEvent.click(screen.getByRole("button", { name: /cancel/i }));

    expect(confirmSpy).toHaveBeenCalled();
    // User declined → still in edit mode.
    expect(screen.getByText(/editing/i)).toBeInTheDocument();
    confirmSpy.mockRestore();
  });

  it("Save opens the save dialog with the dirty count", () => {
    reset();
    renderWithQuery(
      <DoseResponseChart curves={[makeCurve()]} isInteractive />,
    );
    fireEvent.click(screen.getByRole("button", { name: /edit points/i }));
    fireEvent.click(screen.getAllByRole("row")[1]);
    fireEvent.click(screen.getByRole("button", { name: /save 1/i }));

    // Dialog title carries the dirty count.
    expect(
      screen.getByText(/save 1 exclusion change\??/i),
    ).toBeInTheDocument();
  });
});
