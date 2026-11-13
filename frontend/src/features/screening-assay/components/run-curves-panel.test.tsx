import { fireEvent, render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { MEASURED_CURVE_COLORS } from "@/shared/lib/chart-colors";
import type { RunCurves } from "../types";

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

const canEdit = { value: true };
vi.mock("@/shared/hooks/use-current-user", () => ({ useCanEdit: () => canEdit.value }));
vi.mock("./edit-labelling-dialog", () => ({
  EditLabellingDialog: ({ open }: { open: boolean }) =>
    open ? <div data-testid="edit-labelling">edit labelling dialog</div> : null,
}));

import { RunCurvesPanel } from "./run-curves-panel";

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
    expect(screen.getByText("Select positions above to draw their curves")).toBeInTheDocument();
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
      ["Colour", "Highlight", /Distinct/],
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
      filename: "run-curves-r1",
    });
    expect(figure.layout.paper_bgcolor).toBe("#ffffff");
  });

  it("hides the window field in the measured view", () => {
    render(<RunCurvesPanel runId="r1" />);
    expect(screen.queryByLabelText("Window")).not.toBeInTheDocument();
  });

  it("requests view=derivative when the switch is on and shows the window the API used", () => {
    render(<RunCurvesPanel runId="r1" />);
    fireEvent.mouseDown(screen.getByRole("tab", { name: "Derivative" }));
    expect(lastParams()).toMatchObject({ view: "derivative" });
    expect(screen.getByLabelText("Window")).toHaveValue(3.5);
  });

  it("refetches with the edited window on commit, not on each keystroke", () => {
    render(<RunCurvesPanel runId="r1" />);
    fireEvent.mouseDown(screen.getByRole("tab", { name: "Derivative" }));
    const field = screen.getByLabelText("Window");
    fireEvent.change(field, { target: { value: "2" } });
    expect(lastParams()?.window).toBeUndefined();
    fireEvent.blur(field);
    expect(lastParams()).toMatchObject({ view: "derivative", window: 2 });
    expect(screen.getByLabelText("Window")).toHaveValue(2);
    fireEvent.change(field, { target: { value: "4" } });
    expect(lastParams()?.window).toBe(2);
    fireEvent.keyDown(field, { key: "Enter" });
    expect(lastParams()).toMatchObject({ window: 4 });
  });

  it("goes back to the default window when the field is cleared", () => {
    render(<RunCurvesPanel runId="r1" />);
    fireEvent.mouseDown(screen.getByRole("tab", { name: "Derivative" }));
    const field = screen.getByLabelText("Window");
    fireEvent.change(field, { target: { value: "2" } });
    fireEvent.blur(field);
    expect(lastParams()).toMatchObject({ window: 2 });
    fireEvent.change(field, { target: { value: "" } });
    fireEvent.blur(field);
    expect(lastParams()).toMatchObject({ view: "derivative" });
    expect(lastParams()?.window).toBeUndefined();
    expect(screen.getByLabelText("Window")).toHaveValue(3.5);
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
    const field = screen.getByLabelText("Window");
    fireEvent.change(field, { target: { value: "99" } });
    fireEvent.blur(field);
    expect(lastParams()).toMatchObject({ window: 99 });
    expect(screen.getByLabelText("Window")).toHaveValue(2);
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
    fireEvent.change(screen.getByLabelText("Window"), { target: { value: "5" } });
    fireEvent.keyDown(screen.getByLabelText("Window"), { key: "Enter" });
    expect(screen.getByText("Could not load the curves.")).toBeInTheDocument();
    expect(screen.getByLabelText("Window")).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Measured" })).toBeInTheDocument();
    fireEvent.mouseDown(screen.getByRole("tab", { name: "Measured" }));
    expect(screen.queryByText("Could not load the curves.")).not.toBeInTheDocument();
  });

  it("offers Edit labelling beside the selector, disabled with the reason on a locked run", () => {
    const { unmount } = render(
      <RunCurvesPanel runId="r1" run={{ id: "r1", status: "draft", is_locked: false }} />,
    );
    const button = screen.getByRole("button", { name: "Edit labelling" });
    expect(button).toBeEnabled();
    fireEvent.click(button);
    expect(screen.getByTestId("edit-labelling")).toBeInTheDocument();
    unmount();

    render(<RunCurvesPanel runId="r1" run={{ id: "r1", status: "draft", is_locked: true }} />);
    const locked = screen.getByRole("button", { name: "Edit labelling" });
    expect(locked).toBeDisabled();
    expect(locked).toHaveAttribute("title", "The run is locked.");
  });

  it("does not offer Edit labelling to a viewer", () => {
    canEdit.value = false;
    render(<RunCurvesPanel runId="r1" run={{ id: "r1", status: "draft", is_locked: false }} />);
    expect(screen.queryByRole("button", { name: "Edit labelling" })).not.toBeInTheDocument();
  });

  it("does not offer Edit labelling without a run", () => {
    render(<RunCurvesPanel runId="r1" />);
    expect(screen.queryByRole("button", { name: "Edit labelling" })).not.toBeInTheDocument();
  });
});
