import { fireEvent, render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { MEASURED_CURVE_COLORS } from "@/shared/lib/chart-colors";
import type { MeltWindowPosition, MeltingAnalysis, RunCurves } from "../types";

const plotCalls: Array<{ data: Array<Record<string, unknown>>; layout: Record<string, unknown> }> =
  [];
const downloadImage = vi.fn();
vi.mock("@/shared/lib/plotly", () => ({
  Plot: (props: { data: Array<Record<string, unknown>>; layout: Record<string, unknown> }) => {
    plotCalls.push(props);
    return <div data-testid="plot" />;
  },
  getPlotlyGlobal: () => ({ downloadImage }),
}));

const useRunCurves = vi.fn();
vi.mock("../hooks/use-run-curves", () => ({
  useRunCurves: (...args: unknown[]) => useRunCurves(...args),
}));

// Melting steps are covered in melting-steps-panel.test.tsx. Without an
// analysis (it failed to load) the viewer keeps its own position selector.
const melting: { data?: MeltingAnalysis; isLoading?: boolean } = {};
vi.mock("../hooks/use-melting-analysis", () => ({
  useMeltingAnalysis: () => ({ ...melting, refetch: vi.fn() }),
  useAddMeltingStep: () => ({ mutate: vi.fn(), isPending: false }),
  useReviewMeltingStep: () => ({ mutate: vi.fn(), isPending: false }),
}));
vi.mock("@/shared/components/data-grid/data-grid", async () => ({
  DataGrid: (await import("./test-data-grid")).TableGrid,
}));

const canEdit = { value: true };
vi.mock("@/shared/hooks/use-current-user", () => ({ useCanEdit: () => canEdit.value }));
vi.mock("./edit-labelling-dialog", () => ({
  EditLabellingDialog: ({ open }: { open: boolean }) =>
    open ? <div data-testid="edit-labelling">edit labelling dialog</div> : null,
}));

import { RunCurvesPanel } from "./run-curves-panel";
import { gridRow } from "./test-data-grid";

const positions = Array.from({ length: 9 }, (_, i) => ({
  well_id: `w${i + 1}`,
  position: `A${i + 1}`,
  row: "A",
  column: i + 1,
  well_type: i === 0 ? "reference" : "sample",
  registration_number: null,
  position_label: `Position ${i + 1}`,
  label: i === 0 ? "Protein alone" : `ABC-000000${i + 1}`,
  note: i === 0 ? "bubble at start" : null,
  dose: i === 0 ? null : 50,
}));

const curves: RunCurves = {
  run_id: "r1",
  dose_unit: "uM",
  holder: { kind: "cassette", rows: 1, columns: 9, label: "Holder of 9" },
  positions,
  channels: [
    { key: "a", label: "Signal A", x_unit: "°C", y_unit: null, x_label: null },
    { key: "b", label: "Signal B", x_unit: "°C", y_unit: null, x_label: null },
  ],
  channel: "a",
  curves: positions.map((p) => ({
    well_id: p.well_id,
    x: [20, 21, 22],
    y: [1, 2, 3],
    reported:
      p.well_id === "w1"
        ? [
            { kind: "k1", ordinal: 1, label: "Point 1", value: 36.61, unit: "°C" },
            { kind: "k2", ordinal: 1, label: "Point 2", value: 0.004123, unit: "°C" },
          ]
        : [],
  })),
  view: "measured",
  window: null,
};

const RUN = { id: "r1", protocol_id: "p1", status: "draft", is_locked: false } as const;

type Cell = Partial<Omit<MeltWindowPosition, "well_id">>;
/** An analysis with one window "Main" on signal a; `cells` by well id. */
function withAnalysis(cells: Record<string, Cell>, windows = 1) {
  const win = (name: string) => ({
    window: name,
    channel_key: "a",
    low: 30,
    high: 90,
    tm_readout_id: null,
    delta_tm_readout_id: null,
    reference_tm: 60,
    reference_count: 1,
    flags: [],
    positions: positions.map((p) => ({
      well_id: p.well_id,
      tm: null,
      delta_tm: null,
      flags: [],
      ...cells[p.well_id],
    })),
  });
  melting.data = {
    run_id: "r1",
    edit_refusal: null,
    steps: [],
    windows: windows ? [win("Main")] : [],
    step_checks: [],
  };
}

const selectedRows = () =>
  [...document.querySelectorAll("tr[data-row-id]")]
    .filter((tr) => tr.className.includes("bg-primary/10"))
    .map((tr) => tr.getAttribute("data-row-id"));

const drawnWells = () => lastPlot().data.map((t) => t.meta);

function lastParams() {
  return useRunCurves.mock.calls.at(-1)?.[1];
}

function lastPlot() {
  const call = plotCalls.at(-1);
  if (!call) throw new Error("plot not drawn");
  return call;
}

beforeEach(() => {
  canEdit.value = true;
  melting.data = undefined;
  melting.isLoading = false;
  plotCalls.length = 0;
  downloadImage.mockReset();
  useRunCurves.mockReset();
  useRunCurves.mockImplementation((_runId: string, params: { view?: string; window?: number }) => ({
    data:
      params.view === "derivative"
        ? { ...curves, view: "derivative", window: params.window ?? 3.5 }
        : curves,
    isLoading: false,
    isPlaceholderData: false,
  }));
});

describe("RunCurvesPanel", () => {
  it("shows an empty state when nothing is selected", () => {
    render(<RunCurvesPanel runId="r1" />);
    expect(screen.getByText("Select positions above to draw their traces")).toBeInTheDocument();
    expect(screen.queryByTestId("plot")).not.toBeInTheDocument();
    expect(screen.getByText("No positions selected.")).toBeInTheDocument();
  });

  it("requests the chosen channel and keeps the selection", () => {
    render(<RunCurvesPanel runId="r1" />);
    expect(useRunCurves).toHaveBeenCalledWith("r1", expect.anything());
    const slot = screen.getByRole("button", { name: "Position 1" });
    fireEvent.click(slot);
    fireEvent.mouseDown(screen.getByRole("tab", { name: "Signal B" }));
    expect(lastParams()).toMatchObject({ channel: "b" });
    expect(screen.getByRole("button", { name: "Position 1" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
  });

  it("marks the current option of each segmented control as selected", () => {
    render(<RunCurvesPanel runId="r1" />);
    for (const [group, current, other] of [
      ["Signal", "Signal A", "Signal B"],
      ["View", "Measured", "Derivative"],
      ["Reported values", "Lines on", "Off"],
      ["Color", "Highlight", /Distinct/],
    ] as const) {
      const list = screen.getByRole("tablist", { name: group });
      expect(within(list).getByRole("tab", { name: current })).toHaveAttribute(
        "aria-selected",
        "true",
      );
      expect(within(list).getByRole("tab", { name: other })).toHaveAttribute(
        "aria-selected",
        "false",
      );
    }
    fireEvent.mouseDown(screen.getByRole("tab", { name: "Off" }));
    expect(screen.getByRole("tab", { name: "Off" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tab", { name: "Lines on" })).toHaveAttribute("aria-selected", "false");
  });

  it("lists the selected positions in the table with their reported values", () => {
    render(<RunCurvesPanel runId="r1" />);
    fireEvent.click(screen.getByRole("button", { name: "Position 1" }));
    const table = screen.getByRole("table");
    expect(within(table).getByText("Note")).toBeInTheDocument();
    expect(within(table).getByText("Conc. (µM)")).toBeInTheDocument();
    expect(within(table).getByText("Point 1 (°C)")).toBeInTheDocument();
    expect(within(table).getByText("Protein alone")).toBeInTheDocument();
    expect(within(table).getByText("bubble at start")).toBeInTheDocument();
    // The application's number format at four significant figures.
    expect(within(table).getByText("36.61")).toBeInTheDocument();
    expect(within(table).getByText("0.004123")).toBeInTheDocument();
    expect(lastPlot().data).toHaveLength(1);
  });

  it("focuses a position from its table row in the plot and the selector", () => {
    render(<RunCurvesPanel runId="r1" />);
    fireEvent.click(screen.getByRole("button", { name: "Position 1" }));
    fireEvent.click(screen.getByRole("button", { name: "Position 2" }), { metaKey: true });
    const row = within(screen.getByRole("table")).getByText("ABC-0000002").closest("tr");
    if (!row) throw new Error("row not found");
    fireEvent.mouseEnter(row);
    const traces = lastPlot().data as Array<{ line: { color: string }; opacity: number }>;
    expect(traces[1].line.color).toBe(MEASURED_CURVE_COLORS.dark.focus);
    expect(traces[0].opacity).toBe(0.35);
    expect(screen.getByRole("button", { name: "Position 2" })).toHaveAttribute(
      "data-focused",
      "true",
    );
    fireEvent.mouseLeave(row);
    expect((lastPlot().data[0] as { opacity: number }).opacity).toBe(1);
  });

  it("disables distinct colours when more than 8 are selected", () => {
    render(<RunCurvesPanel runId="r1" />);
    fireEvent.click(screen.getByRole("button", { name: "Position 1" }));
    fireEvent.mouseDown(screen.getByRole("tab", { name: /Distinct/ }));
    const traces = lastPlot().data as Array<{ line: { color: string } }>;
    expect(traces[0].line.color).toBe(MEASURED_CURVE_COLORS.dark.series[0]);
    fireEvent.click(screen.getByRole("button", { name: "All" }));
    expect(screen.getByRole("tab", { name: /Distinct/ })).toBeDisabled();
    expect(screen.getAllByText(/More than 8 selected/).length).toBeGreaterThan(0);
    const after = lastPlot().data as Array<{ line: { color: string } }>;
    expect(after[0].line.color).toBe(MEASURED_CURVE_COLORS.dark.reference);
  });

  it("exports the figure on a white background at 1200 by 600", () => {
    render(<RunCurvesPanel runId="r1" />);
    fireEvent.click(screen.getByRole("button", { name: "Position 1" }));
    fireEvent.click(screen.getByRole("button", { name: "PNG" }));
    const [figure, opts] = downloadImage.mock.calls[0];
    expect(opts).toMatchObject({
      format: "png",
      width: 1200,
      height: 600,
      filename: "traces-run-r1",
    });
    expect(figure.layout.paper_bgcolor).toBe("#ffffff");
  });

  it("hides the window field in the measured view", () => {
    render(<RunCurvesPanel runId="r1" />);
    expect(screen.queryByLabelText("Smoothing window")).not.toBeInTheDocument();
  });

  it("requests view=derivative when the switch is on and shows the window the API used", () => {
    render(<RunCurvesPanel runId="r1" />);
    fireEvent.mouseDown(screen.getByRole("tab", { name: "Derivative" }));
    expect(lastParams()).toMatchObject({ view: "derivative" });
    expect(screen.getByLabelText("Smoothing window")).toHaveValue(3.5);
  });

  it("refetches with the edited window on commit, not on each keystroke", () => {
    render(<RunCurvesPanel runId="r1" />);
    fireEvent.mouseDown(screen.getByRole("tab", { name: "Derivative" }));
    const field = screen.getByLabelText("Smoothing window");
    fireEvent.change(field, { target: { value: "2" } });
    expect(lastParams()?.window).toBeUndefined();
    fireEvent.blur(field);
    expect(lastParams()).toMatchObject({ view: "derivative", window: 2 });
    expect(screen.getByLabelText("Smoothing window")).toHaveValue(2);
    fireEvent.change(field, { target: { value: "4" } });
    expect(lastParams()?.window).toBe(2);
    fireEvent.keyDown(field, { key: "Enter" });
    expect(lastParams()).toMatchObject({ window: 4 });
  });

  it("goes back to the default window when the field is cleared", () => {
    render(<RunCurvesPanel runId="r1" />);
    fireEvent.mouseDown(screen.getByRole("tab", { name: "Derivative" }));
    const field = screen.getByLabelText("Smoothing window");
    fireEvent.change(field, { target: { value: "2" } });
    fireEvent.blur(field);
    expect(lastParams()).toMatchObject({ window: 2 });
    fireEvent.change(field, { target: { value: "" } });
    fireEvent.blur(field);
    expect(lastParams()).toMatchObject({ view: "derivative" });
    expect(lastParams()?.window).toBeUndefined();
    expect(screen.getByLabelText("Smoothing window")).toHaveValue(3.5);
  });

  it("shows the window the API used when it clamps an oversized one", () => {
    useRunCurves.mockImplementation(
      (_runId: string, params: { view?: string; window?: number }) => ({
        data:
          params.view === "derivative"
            ? { ...curves, view: "derivative", window: Math.min(params.window ?? 3.5, 2) }
            : curves,
        isLoading: false,
        isPlaceholderData: false,
      }),
    );
    render(<RunCurvesPanel runId="r1" />);
    fireEvent.mouseDown(screen.getByRole("tab", { name: "Derivative" }));
    const field = screen.getByLabelText("Smoothing window");
    fireEvent.change(field, { target: { value: "99" } });
    fireEvent.blur(field);
    expect(lastParams()).toMatchObject({ window: 99 });
    expect(screen.getByLabelText("Smoothing window")).toHaveValue(2);
  });

  it("keeps the toolbar on screen when a refetch with a window fails", () => {
    useRunCurves.mockImplementation((_runId: string, params: { view?: string; window?: number }) =>
      params.window === 5
        ? { data: undefined, error: new Error("boom"), isLoading: false, isPlaceholderData: false }
        : {
            data:
              params.view === "derivative"
                ? { ...curves, view: "derivative", window: params.window ?? 3.5 }
                : curves,
            isLoading: false,
            isPlaceholderData: false,
          },
    );
    render(<RunCurvesPanel runId="r1" />);
    fireEvent.mouseDown(screen.getByRole("tab", { name: "Derivative" }));
    fireEvent.change(screen.getByLabelText("Smoothing window"), { target: { value: "5" } });
    fireEvent.keyDown(screen.getByLabelText("Smoothing window"), { key: "Enter" });
    expect(
      screen.getByText("Could not load the traces. Reload the page and try again."),
    ).toBeInTheDocument();
    expect(screen.getByLabelText("Smoothing window")).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Measured" })).toBeInTheDocument();
    fireEvent.mouseDown(screen.getByRole("tab", { name: "Measured" }));
    expect(
      screen.queryByText("Could not load the traces. Reload the page and try again."),
    ).not.toBeInTheDocument();
  });

  it("offers Edit labelling beside the selector, disabled with the reason on a locked run", () => {
    const { unmount } = render(<RunCurvesPanel runId="r1" run={RUN} />);
    const button = screen.getByRole("button", { name: "Edit labeling" });
    expect(button).toBeEnabled();
    fireEvent.click(button);
    expect(screen.getByTestId("edit-labelling")).toBeInTheDocument();
    unmount();

    render(<RunCurvesPanel runId="r1" run={{ ...RUN, is_locked: true }} />);
    const locked = screen.getByRole("button", { name: "Edit labeling" });
    expect(locked).toBeDisabled();
    expect(locked).toHaveAttribute("title", "The run is locked.");
  });

  it("does not offer Edit labelling to a viewer", () => {
    canEdit.value = false;
    render(<RunCurvesPanel runId="r1" run={RUN} />);
    expect(screen.queryByRole("button", { name: "Edit labeling" })).not.toBeInTheDocument();
  });

  it("does not offer Edit labelling without a run", () => {
    render(<RunCurvesPanel runId="r1" />);
    expect(screen.queryByRole("button", { name: "Edit labeling" })).not.toBeInTheDocument();
  });

  describe("with the results", () => {
    it("selects the first position needing review on load", () => {
      withAnalysis({
        w2: { tm: 59, delta_tm: -1 },
        w3: { flags: ["no_step_in_window"] },
        w4: { tm: 65, delta_tm: 5 },
        w5: { flags: ["several_steps_in_window"] },
      });
      render(<RunCurvesPanel runId="r1" />);
      expect(selectedRows()).toEqual(["w3"]);
      expect(screen.queryByRole("button", { name: "Position 3" })).not.toBeInTheDocument();
    });

    it("falls back to the largest shift, then the first sample", () => {
      withAnalysis({
        w2: { tm: 59, delta_tm: -1 },
        w4: { tm: 65, delta_tm: 5 },
        w6: { tm: 53, delta_tm: -7 },
      });
      const { unmount } = render(<RunCurvesPanel runId="r1" />);
      expect(selectedRows()).toEqual(["w6"]);
      unmount();

      withAnalysis({});
      render(<RunCurvesPanel runId="r1" />);
      expect(selectedRows()).toEqual(["w2"]);
    });

    it("reference traces are on by default", () => {
      withAnalysis({ w2: { tm: 59, delta_tm: -1 } });
      render(<RunCurvesPanel runId="r1" />);
      expect(screen.getByRole("switch", { name: "Reference traces" })).toBeChecked();
      expect(drawnWells()).toEqual(expect.arrayContaining(["w1", "w2"]));
    });

    it("filtering keeps the selection", () => {
      withAnalysis({ w2: { tm: 55, delta_tm: -5 }, w3: { flags: ["no_step_in_window"] } });
      render(<RunCurvesPanel runId="r1" />);
      expect(selectedRows()).toEqual(["w3"]);
      fireEvent.click(screen.getByRole("button", { name: "1 down" }));
      expect(document.querySelector('tr[data-row-id="w3"]')).toBeNull();
      expect(drawnWells()).toContain("w3");
    });

    it("hints at the results when nothing is selected", () => {
      withAnalysis({ w2: { tm: 59, delta_tm: -1 } });
      render(<RunCurvesPanel runId="r1" />);
      expect(
        screen.queryByText("Select a sample in the results to see its trace and steps."),
      ).not.toBeInTheDocument();
      fireEvent.click(gridRow("Position 2"), { metaKey: true });
      expect(selectedRows()).toEqual([]);
      expect(
        screen.getByText("Select a sample in the results to see its trace and steps."),
      ).toBeInTheDocument();
    });

    it("edit labeling sits in the results header", () => {
      withAnalysis({});
      render(<RunCurvesPanel runId="r1" run={RUN} />);
      const results = screen.getByRole("heading", { name: "Results" }).closest("section");
      if (!results) throw new Error("no results section");
      expect(within(results).getByRole("button", { name: "Edit labeling" })).toBeEnabled();
      expect(screen.getAllByRole("button", { name: "Edit labeling" })).toHaveLength(1);
    });

    it("links the no-window note to the protocol's Design tab", () => {
      withAnalysis({}, 0);
      render(<RunCurvesPanel runId="r1" run={RUN} />);
      expect(
        screen.getByRole("link", {
          name: "No temperature window on this signal — add one on the protocol's Design tab",
        }),
      ).toHaveAttribute("href", "/assays/protocols/p1#design");
    });

    it("shows a placeholder while the results load", () => {
      melting.isLoading = true;
      render(<RunCurvesPanel runId="r1" />);
      expect(screen.getByTestId("results-loading")).toBeInTheDocument();
      expect(screen.queryByRole("button", { name: "Position 1" })).not.toBeInTheDocument();
    });
  });
});
