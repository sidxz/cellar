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
  useGetCurveEditHistoryApiV1DoseResponseCurvesCurveIdEditHistoryGet: () => ({
    data: { events: [] },
    isLoading: false,
  }),
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
  marker?: {
    symbol?: string;
    color?: string;
    size?: number;
    line?: { color?: string; width?: number };
    opacity?: number;
  };
  x?: number[];
  y?: number[];
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

describe("<DoseResponseChart /> — keyboard shortcuts in edit mode", () => {
  it("Cmd+Z (or Ctrl+Z) undoes the last toggle while in edit mode", () => {
    reset();
    renderWithQuery(
      <DoseResponseChart curves={[makeCurve()]} isInteractive />,
    );
    fireEvent.click(screen.getByRole("button", { name: /edit points/i }));
    // Toggle one point → 1 unsaved change.
    fireEvent.click(screen.getAllByRole("row")[1]);
    expect(
      screen.getByText(/editing — 1 unsaved change(?!s)/i),
    ).toBeInTheDocument();

    // Fire both meta + ctrl variants so we don't have to mock navigator.platform.
    fireEvent.keyDown(document, { key: "z", metaKey: true });
    fireEvent.keyDown(document, { key: "z", ctrlKey: true });

    expect(
      screen.getByText(/editing — 0 unsaved changes/i),
    ).toBeInTheDocument();
  });

  it("Cmd+Shift+Z redoes after an undo", () => {
    reset();
    renderWithQuery(
      <DoseResponseChart curves={[makeCurve()]} isInteractive />,
    );
    fireEvent.click(screen.getByRole("button", { name: /edit points/i }));
    fireEvent.click(screen.getAllByRole("row")[1]);

    // Undo (try both modifiers).
    fireEvent.keyDown(document, { key: "z", metaKey: true });
    fireEvent.keyDown(document, { key: "z", ctrlKey: true });
    expect(
      screen.getByText(/editing — 0 unsaved changes/i),
    ).toBeInTheDocument();

    // Redo (try both modifiers).
    fireEvent.keyDown(document, { key: "z", metaKey: true, shiftKey: true });
    fireEvent.keyDown(document, { key: "z", ctrlKey: true, shiftKey: true });
    expect(
      screen.getByText(/editing — 1 unsaved change(?!s)/i),
    ).toBeInTheDocument();
  });

  it("Esc with no draft exits edit mode without confirm", () => {
    reset();
    const confirmSpy = vi.spyOn(window, "confirm");
    renderWithQuery(
      <DoseResponseChart curves={[makeCurve()]} isInteractive />,
    );
    fireEvent.click(screen.getByRole("button", { name: /edit points/i }));
    expect(screen.getByText(/editing/i)).toBeInTheDocument();

    fireEvent.keyDown(document, { key: "Escape" });

    expect(confirmSpy).not.toHaveBeenCalled();
    expect(screen.queryByText(/editing/i)).not.toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /edit points/i }),
    ).toBeInTheDocument();
    confirmSpy.mockRestore();
  });

  it("Esc with a dirty draft prompts confirm; saying no keeps edit mode", () => {
    reset();
    const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(false);
    renderWithQuery(
      <DoseResponseChart curves={[makeCurve()]} isInteractive />,
    );
    fireEvent.click(screen.getByRole("button", { name: /edit points/i }));
    fireEvent.click(screen.getAllByRole("row")[1]);

    fireEvent.keyDown(document, { key: "Escape" });

    expect(confirmSpy).toHaveBeenCalled();
    expect(screen.getByText(/editing/i)).toBeInTheDocument();
    confirmSpy.mockRestore();
  });

  it("does not fire when not in edit mode", () => {
    reset();
    renderWithQuery(
      <DoseResponseChart curves={[makeCurve()]} isInteractive />,
    );
    // No edit mode yet — Esc should be a no-op (Edit Points stays visible).
    fireEvent.keyDown(document, { key: "Escape" });
    expect(
      screen.getByRole("button", { name: /edit points/i }),
    ).toBeInTheDocument();
  });
});

describe("<DoseResponseChart /> — locked-run guard", () => {
  it("disables Edit Points and shows Locked badge when runIsLocked is true", () => {
    reset();
    renderWithQuery(
      <DoseResponseChart curves={[makeCurve()]} isInteractive runIsLocked />,
    );
    const editBtn = screen.getByRole("button", { name: /edit points/i });
    expect(editBtn).toBeDisabled();
    expect(editBtn).toHaveAttribute("title", "Unapprove run to edit curves");
    expect(screen.getByText(/^locked$/i)).toBeInTheDocument();
  });

  it("Edit Points stays enabled when runIsLocked is false or undefined", () => {
    reset();
    renderWithQuery(
      <DoseResponseChart curves={[makeCurve()]} isInteractive />,
    );
    expect(
      screen.getByRole("button", { name: /edit points/i }),
    ).toBeEnabled();
    // No "Locked" badge when the run isn't locked.
    expect(screen.queryByText(/^locked$/i)).not.toBeInTheDocument();
  });
});

describe("<DoseResponseChart /> — auto-3σ suggestion markers", () => {
  it("renders auto-3σ suggestions as yellow-halo markers, distinct from manual exclusions", () => {
    reset();
    const curve = makeCurve({
      raw_data: [
        { x: 0.01, y: 5 },
        { x: 0.1, y: 30 },
        { x: 1, y: 80 },
        { x: 10, y: 95 },
      ],
      excluded_points: [
        {
          idx: 1,
          source: "auto_3sigma",
          excluded: false,
          reason: "auto_3sigma",
          note: null,
          author_id: null,
          ts: "2026-05-19T10:00:00Z",
          concentration: null,
          response: null,
        },
        {
          idx: 2,
          source: "manual",
          excluded: true,
          reason: "outlier",
          note: null,
          author_id: "u1",
          ts: "2026-05-19T10:00:00Z",
          concentration: null,
          response: null,
        },
      ],
    });
    renderWithQuery(<DoseResponseChart curves={[curve]} />);

    const traces = plotCalls[0].data as Trace[];
    // Suggestion trace: amber open circle.
    const suggestionTrace = traces.find((t) => /suggested 3σ/i.test(t.name ?? ""));
    expect(suggestionTrace).toBeDefined();
    expect(suggestionTrace?.marker?.symbol).toBe("circle-open");
    // Color matches the warning token (amber-500 / #f59e0b).
    expect(suggestionTrace?.marker?.color).toBe("#f59e0b");
    expect(suggestionTrace?.x).toEqual([0.1]);
    expect(suggestionTrace?.y).toEqual([30]);

    // Manual exclusion remains an X marker — separate trace.
    const manualTrace = traces.find(
      (t) => /\(excluded\)$/i.test(t.name ?? "") && t.marker?.symbol === "x",
    );
    expect(manualTrace).toBeDefined();
    expect(manualTrace?.x).toEqual([1]);
    expect(manualTrace?.y).toEqual([80]);
  });

  it("hides suggestion idxs from the included-points trace so the halo isn't drawn over a filled dot", () => {
    reset();
    const curve = makeCurve({
      raw_data: [
        { x: 0.01, y: 5 },
        { x: 0.1, y: 30 },
        { x: 1, y: 80 },
        { x: 10, y: 95 },
      ],
      excluded_points: [
        {
          idx: 2,
          source: "auto_3sigma",
          excluded: false,
          reason: "auto_3sigma",
          note: null,
          author_id: null,
          ts: "2026-05-19T10:00:00Z",
        },
      ],
    });
    renderWithQuery(<DoseResponseChart curves={[curve]} />);

    const traces = plotCalls[0].data as Trace[];
    // Find the primary "included" markers trace — it's the marker trace
    // whose name carries the curve-type label (e.g. "CV-00001 (IC50)")
    // and no "(excluded)" / "(auto-excluded)" / "(suggested 3σ)" suffix.
    const includedTrace = traces.find(
      (t) =>
        t.mode === "markers" &&
        t.marker?.symbol === "circle" &&
        typeof t.name === "string" &&
        !/excluded|suggested|replicates|fit$/i.test(t.name),
    );
    expect(includedTrace).toBeDefined();
    // 4 raw_data points minus 1 suggestion → 3 in the included trace.
    expect(includedTrace?.x).toHaveLength(3);
    // The suggestion was at idx=2 → raw_data[2] = (1, 80); confirm those
    // coords don't show up in the included trace.
    expect(includedTrace?.x).not.toContain(1);
    expect(includedTrace?.y).not.toContain(80);
  });

  it("legacy excluded_points (idx=null + concentration/response) still render as X markers", () => {
    reset();
    const curve = makeCurve({
      raw_data: [
        { x: 0.01, y: 5 },
        { x: 0.1, y: 30 },
      ],
      excluded_points: [
        // Legacy backfilled row: no idx, only scalar coords. Treated as
        // accepted auto-exclusion.
        {
          idx: null,
          source: "auto_3sigma",
          excluded: true,
          reason: "auto_3sigma",
          concentration: 5.0,
          response: 88,
        },
      ],
    });
    renderWithQuery(<DoseResponseChart curves={[curve]} />);

    const traces = plotCalls[0].data as Trace[];
    const autoTrace = traces.find(
      (t) => /\(auto-excluded\)$/i.test(t.name ?? "") && t.marker?.symbol === "diamond",
    );
    expect(autoTrace).toBeDefined();
    expect(autoTrace?.x).toEqual([5.0]);
    expect(autoTrace?.y).toEqual([88]);
  });

  it("entries with the legacy wire shape (reason only, no source/excluded) keep rendering as accepted exclusions", () => {
    reset();
    const curve = makeCurve({
      raw_data: [{ x: 0.01, y: 5 }],
      excluded_points: [
        // Pre-Task-2.7 shape: reason-only, no source / excluded fields.
        { idx: null, reason: "auto_3sigma", concentration: 5.0, response: 88 },
      ],
    });
    renderWithQuery(<DoseResponseChart curves={[curve]} />);

    const traces = plotCalls[0].data as Trace[];
    // Legacy reason="auto_3sigma" → still rendered as diamond auto-exclude.
    const autoTrace = traces.find(
      (t) => /\(auto-excluded\)$/i.test(t.name ?? "") && t.marker?.symbol === "diamond",
    );
    expect(autoTrace).toBeDefined();
    // No suggestion trace — legacy entries default to excluded=true.
    const suggestionTrace = traces.find((t) => /suggested 3σ/i.test(t.name ?? ""));
    expect(suggestionTrace).toBeUndefined();
  });
});

// ─── FE↔BE idx-domain alignment (post-save bug fix) ─────────────────────────
// The BE's build_points_with_exclusions merges curve.raw_data +
// curve.excluded_points and sorts by concentration; the excluded_indices
// the FE sends index INTO THAT MERGED SET. After any save with manual
// exclusions the BE's curve fitter writes raw_data = active-only, so
// raw_data shrinks while the captured set stays full. Pre-fix the FE
// computed "position in raw_data" for click-targets, which silently
// diverged from the BE's domain after the first save. The chart now uses
// the captured set everywhere — these tests cover the post-save path.

describe("<DoseResponseChart /> — captured-set idx domain (post-save)", () => {
  it("inventory rows render in concentration-sorted order across raw_data + excluded_points", () => {
    reset();
    // Mimic the post-save shape: raw_data has 3 points (the 0.1 was
    // excluded on a prior save and removed from the active set), and
    // excluded_points carries the missing point with its coords.
    const curve = makeCurve({
      raw_data: [
        { x: 0.001, y: 2 },
        { x: 0.01, y: 5 },
        { x: 1.0, y: 50 },
      ],
      excluded_points: [
        {
          idx: 2,
          source: "manual",
          excluded: true,
          reason: "outlier",
          note: null,
          author_id: "u1",
          ts: "2026-05-19T10:00:00Z",
          concentration: 0.1,
          response: 99,
        },
      ],
    });
    renderWithQuery(
      <DoseResponseChart curves={[curve]} isInteractive />,
    );
    fireEvent.click(screen.getByRole("button", { name: /edit points/i }));

    // Inventory has 4 rows (header + 4 data rows in captured-sorted order).
    const rows = screen.getAllByRole("row");
    expect(rows).toHaveLength(5);
    // Row 1 = 0.001 M, row 2 = 0.01 M, row 3 = 0.1 M (the excluded one),
    // row 4 = 1.0 M. The 0.1 M row appears in the middle — sorted by
    // concentration across raw_data + excluded_points, NOT raw_data-only
    // order (which would put 0.1 anywhere or not at all).
    const inventoryTable = screen.getByLabelText(/point inventory/i);
    const tableText = inventoryTable.textContent ?? "";
    // The 0.1 M point's coordinates should be visible inside the inventory.
    // formatConcentration uses toPrecision(3) for values ≥ 1e-3.
    expect(tableText).toMatch(/0\.100 M/);
    // The excluded (manual) status pill should appear once (for the 0.1 M row).
    expect(screen.getByText(/excluded \(manual\)/i)).toBeInTheDocument();
    // Sanity-check the row ORDER: row 3 (0-indexed 2 after header) should
    // be the 0.1 M point — proving the inventory renders in captured-sorted
    // order (across raw_data + excluded_points) rather than raw-data-only
    // order (where 0.1 wouldn't appear at all).
    expect(rows[3].textContent ?? "").toMatch(/0\.100 M/);
    expect(rows[3].textContent ?? "").toMatch(/excluded \(manual\)/i);
  });

  it("after a prior save, clicking the inventory row for 1.0 sends captured-set idx=3 (not raw_data idx=2)", () => {
    reset();
    // Post-save shape: 3 active points + 1 excluded (the 0.1 point).
    // Captured-sorted order: [0.001, 0.01, 0.1(excl), 1.0]. The 1.0 point
    // sits at capturedIdx=3 (last) while its raw_data position is 2 (3rd).
    // Pre-fix the FE would send idx=2 here, and the BE would interpret
    // that as "exclude the 0.1 point" (the 3rd in captured-sorted order).
    const curve = makeCurve({
      raw_data: [
        { x: 0.001, y: 2 },
        { x: 0.01, y: 5 },
        { x: 1.0, y: 50 },
      ],
      excluded_points: [
        {
          idx: 2,
          source: "manual",
          excluded: true,
          reason: "outlier",
          note: null,
          author_id: "u1",
          ts: "2026-05-19T10:00:00Z",
          concentration: 0.1,
          response: 99,
        },
      ],
    });
    renderWithQuery(
      <DoseResponseChart curves={[curve]} isInteractive />,
    );
    fireEvent.click(screen.getByRole("button", { name: /edit points/i }));

    // Click the LAST inventory row (the 1.0 point — capturedIdx=3).
    const rows = screen.getAllByRole("row");
    // rows = [header, 0.001, 0.01, 0.1(excl), 1.0]
    fireEvent.click(rows[4]);

    // The new draft exclusion should reflect capturedIdx=3. The chart's
    // SummaryCard counter renders "N excluded" — after this toggle the
    // count should be 2 (the prior 0.1 exclusion + the new 1.0 exclusion).
    // Pre-fix the FE would have toggled idx=2 → which collides with the
    // existing 0.1 exclusion → removing it → counter would say 0 excluded.
    expect(screen.getByText(/2 excluded/i)).toBeInTheDocument();
  });

  it("after a prior save, the included-trace markers carry the correct captured-set idxs", () => {
    reset();
    const curve = makeCurve({
      raw_data: [
        { x: 0.001, y: 2 },
        { x: 0.01, y: 5 },
        { x: 1.0, y: 50 },
      ],
      excluded_points: [
        {
          idx: 2,
          source: "manual",
          excluded: true,
          reason: "outlier",
          note: null,
          author_id: "u1",
          ts: "2026-05-19T10:00:00Z",
          concentration: 0.1,
          response: 99,
        },
      ],
    });
    renderWithQuery(<DoseResponseChart curves={[curve]} isInteractive />);

    const traces = plotCalls[plotCalls.length - 1].data as Trace[];
    // Included-trace marker positions must reflect raw_data points in
    // concentration-sorted order: 0.001, 0.01, 1.0.
    const includedTrace = traces.find(
      (t) =>
        t.mode === "markers" &&
        t.marker?.symbol === "circle" &&
        typeof t.name === "string" &&
        !/excluded|suggested|replicates|fit$/i.test(t.name),
    );
    expect(includedTrace).toBeDefined();
    expect(includedTrace?.x).toEqual([0.001, 0.01, 1.0]);
    // Manual-excluded trace renders the 0.1 point (which is NOT in raw_data
    // anymore — it lives only in excluded_points).
    const excludedTrace = traces.find(
      (t) =>
        t.mode === "markers" &&
        t.marker?.symbol === "x" &&
        /\(excluded\)$/i.test(t.name ?? ""),
    );
    expect(excludedTrace).toBeDefined();
    expect(excludedTrace?.x).toEqual([0.1]);
    expect(excludedTrace?.y).toEqual([99]);
  });
});
