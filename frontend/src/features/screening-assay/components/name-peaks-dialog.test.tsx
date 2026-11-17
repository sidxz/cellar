import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { type ReactNode, useState } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "@/shared/lib/api/custom-instance";
import { curveSetFromRun } from "../lib/curve-plot";
import type { MeltWindow, MeltingAnalysis, MeltingStep, RunCurves } from "../types";

const plots: {
  data: Record<string, unknown>[];
  layout: { shapes: Record<string, unknown>[] };
  onClick?: (e: unknown) => void;
}[] = [];
vi.mock("@/shared/lib/plotly", () => ({
  Plot: (p: (typeof plots)[number]) => {
    plots.push(p);
    return <div data-testid="plot" />;
  },
}));

const customInstance = vi.fn();
vi.mock("@/shared/lib/api/custom-instance", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/shared/lib/api/custom-instance")>()),
  customInstance: (...args: unknown[]) => customInstance(...args),
}));

// Radix Select does not open under jsdom; a native select keeps the value contract.
vi.mock("@/shared/components/ui/select", () => ({
  Select: ({
    value,
    onValueChange,
    children,
  }: {
    value: string;
    onValueChange: (v: string) => void;
    children: ReactNode;
  }) => (
    <select aria-label="Reference" value={value} onChange={(e) => onValueChange(e.target.value)}>
      {children}
    </select>
  ),
  SelectTrigger: () => null,
  SelectValue: () => null,
  SelectContent: ({ children }: { children: ReactNode }) => <>{children}</>,
  SelectItem: ({ value, children }: { value: string; children: ReactNode }) => (
    <option value={value}>{children}</option>
  ),
}));

import { NamePeaksDialog } from "./name-peaks-dialog";

const position = (id: string, column: number, type: string, label: string | null) => ({
  well_id: id,
  row: "A",
  column,
  well_type: type,
  position_label: `Capillary ${column}`,
  label,
});
const RUN = {
  run_id: "run1",
  dose_unit: "uM",
  holder: { kind: "cassette", rows: 1, columns: 3, label: "Holder of 3" },
  // Out of holder order on purpose: Capillary 1 is the first reference.
  positions: [
    position("r2", 3, "reference", null),
    position("r1", 1, "reference", "MadR"),
    position("s1", 2, "sample", "CC-1"),
  ],
  channels: [{ key: "a", label: "Ratio", x_unit: "°C", y_unit: null, x_label: null }],
  channel: "a",
  curves: [
    { well_id: "r1", x: [25, 36.6, 55, 71.3, 95], y: [1, 2, 3, 4, 5], reported: [] },
    { well_id: "r2", x: [30, 64.2, 90], y: [1, 2, 3], reported: [] },
    { well_id: "s1", x: [25, 95], y: [1, 2], reported: [] },
  ],
  view: "measured",
  window: null,
} as unknown as RunCurves;

const step = (id: string, well: string, value: number, over: Partial<MeltingStep> = {}) =>
  ({
    id,
    well_id: well,
    channel_key: "a",
    source: "instrument",
    value,
    status: "unreviewed",
    ...over,
  }) as MeltingStep;
const STEPS = [
  step("p2", "r1", 71.3, { status: "accepted" }),
  step("p1", "r1", 36.6),
  step("p3", "r1", 60, { status: "rejected" }),
  step("p4", "r1", 50, { channel_key: "b" }),
  step("p5", "r2", 64.2, { source: "manual", status: "accepted" }),
  step("p6", "s1", 62),
];
const win = (window: string, low: number, high: number, channel = "a") =>
  ({ window, channel_key: channel, low, high, positions: [] }) as unknown as MeltWindow;
const analysisOf = (over: Partial<MeltingAnalysis> = {}) =>
  ({
    run_id: "run1",
    edit_refusal: null,
    steps: STEPS,
    windows: [],
    step_checks: [],
    outside_every_window: [],
    ...over,
  }) as MeltingAnalysis;

const ANALYSIS_KEY = ["melting-analysis", "run1"];
const PROTOCOL_KEY = ["protocols", "p1"];
let qc: QueryClient;
const onOpenChange = vi.fn();

function dialog(
  over: { run?: RunCurves; analysis?: MeltingAnalysis; canRecalculate?: boolean } = {},
) {
  return (
    <NamePeaksDialog
      open
      onOpenChange={onOpenChange}
      runId="run1"
      protocolId="p1"
      set={curveSetFromRun(over.run ?? RUN)}
      analysis={over.analysis ?? analysisOf()}
      canRecalculate={over.canRecalculate ?? true}
    />
  );
}
const wrapper = ({ children }: { children: ReactNode }) => (
  <QueryClientProvider client={qc}>{children}</QueryClientProvider>
);
function renderDialog(over: Parameters<typeof dialog>[0] = {}) {
  return render(dialog(over), { wrapper });
}
/** As on the page: closing takes the dialog away. */
function Closing() {
  const [open, setOpen] = useState(true);
  return (
    <NamePeaksDialog
      {...dialog().props}
      open={open}
      onOpenChange={(next: boolean) => {
        onOpenChange(next);
        setOpen(next);
      }}
    />
  );
}

const peakRow = (temperature: string) =>
  within(screen.getByRole("group", { name: `Peak at ${temperature} °C` }));
const freeRows = () => screen.getAllByRole("group", { name: "Transition without a peak" });
const rowNames = () => screen.getAllByRole("group").map((g) => g.getAttribute("aria-label"));
const type = (row: ReturnType<typeof within>, label: string, value: string) =>
  fireEvent.change(row.getByLabelText(label), { target: { value } });
const save = () => screen.getByRole("button", { name: "Save transitions" });
const existing = () => screen.getByTestId("existing-windows");
const lastPlot = () => {
  const plot = plots.at(-1);
  if (!plot) throw new Error("plot not drawn");
  return plot;
};
const bands = () =>
  lastPlot()
    .layout.shapes.filter((s) => s.type === "rect")
    .map((s) => [s.x0, s.x1]);
const clickTrace = (x: number) =>
  act(() => lastPlot().onClick?.({ points: [{ x, data: { meta: "r1" } }] }));
const requests = (path: string) =>
  customInstance.mock.calls.map(([c]) => c).filter((c) => c.url.endsWith(path));

beforeEach(() => {
  plots.length = 0;
  customInstance.mockReset();
  customInstance.mockResolvedValue({});
  onOpenChange.mockReset();
  qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  qc.setQueryData(ANALYSIS_KEY, analysisOf());
  qc.setQueryData(PROTOCOL_KEY, {});
});

describe("NamePeaksDialog", () => {
  it("names the signal and starts on the first reference in holder order", () => {
    renderDialog();
    expect(screen.getByRole("heading", { name: "Name transitions · Ratio" })).toBeInTheDocument();
    expect(screen.getByRole("dialog")).toHaveAccessibleDescription(
      "Name the reference's peaks. Each named row becomes a transition on the protocol, with the temperature range it is looked for in. A row without a name creates nothing.",
    );
    const chooser = screen.getByLabelText("Reference");
    expect(chooser).toHaveValue("r1");
    expect(within(chooser).getAllByRole("option")).toHaveLength(2);
    expect(within(chooser).getByRole("option", { name: "Capillary 1 · MadR" })).toBeInTheDocument();
  });

  it("has no chooser for a single reference", () => {
    renderDialog({ run: { ...RUN, positions: RUN.positions.slice(1) } });
    expect(screen.queryByLabelText("Reference")).not.toBeInTheDocument();
    expect(screen.getByText("Reference: Capillary 1 · MadR")).toBeInTheDocument();
  });

  it("gives each counted peak of the reference a row with an empty name and a proposed range", () => {
    renderDialog();
    // Not the rejected peak, the other signal's, or another position's.
    expect(rowNames()).toEqual(["Peak at 36.6 °C", "Peak at 71.3 °C"]);
    const first = peakRow("36.6");
    expect(first.getByText("From instrument")).toBeInTheDocument();
    expect(first.getByLabelText("Name")).toHaveValue("");
    expect(first.getByLabelText("Name")).not.toHaveAttribute("placeholder");
    expect(first.getByLabelText("Low (°C)")).toHaveValue(25);
    expect(first.getByLabelText("High (°C)")).toHaveValue(54);
    expect(first.getByLabelText("Tm")).toBeChecked();
    expect(first.getByLabelText("ΔTm")).toBeChecked();
    expect(peakRow("71.3").getByLabelText("Low (°C)")).toHaveValue(54);
    expect(peakRow("71.3").getByLabelText("High (°C)")).toHaveValue(95);
    expect(save()).toBeDisabled();
  });

  it("proposes from the chosen reference alone", () => {
    renderDialog();
    fireEvent.change(screen.getByLabelText("Reference"), { target: { value: "r2" } });
    expect(rowNames()).toEqual(["Peak at 64.2 °C"]);
    const row = peakRow("64.2");
    expect(row.getByText("Placed by hand")).toBeInTheDocument();
    expect(row.getByLabelText("Low (°C)")).toHaveValue(30);
    expect(row.getByLabelText("High (°C)")).toHaveValue(90);
    expect(lastPlot().data.map((t) => t.meta)).toEqual(["r2"]);
  });

  it("lists the signal's windows read-only and leaves their peaks out", () => {
    renderDialog({
      analysis: analysisOf({ windows: [win("Main", 50, 85), win("Other", 20, 40, "b")] }),
    });
    expect(within(existing()).getByText("Main 50–85 °C")).toBeInTheDocument();
    expect(within(existing()).queryByText(/Other/)).not.toBeInTheDocument();
    expect(
      screen.getByRole("link", {
        name: "Changing a published transition's range needs a new protocol version",
      }),
    ).toHaveAttribute("href", "/assays/protocols/p1#setup");
    // 71.3 is in Main; the other range is cut back to Main's limit.
    expect(rowNames()).toEqual(["Peak at 36.6 °C"]);
    expect(peakRow("36.6").getByLabelText("High (°C)")).toHaveValue(50);
  });

  it("says when the signal has no window", () => {
    renderDialog();
    expect(existing()).toHaveTextContent("Transitions already named on this signal: none");
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
  });

  it("draws the reference's trace with its peaks and one band per row, following the numbers", () => {
    renderDialog();
    expect(lastPlot().data.map((t) => t.meta)).toEqual(["r1"]);
    expect(bands()).toEqual([
      [25, 54],
      [54, 95],
    ]);
    const peaks = lastPlot()
      .layout.shapes.filter((s) => s.type === "line")
      .map((s) => s.x0);
    expect(peaks).toEqual([36.6, 71.3]);
    type(peakRow("36.6"), "High (°C)", "48");
    expect(bands()).toEqual([
      [25, 48],
      [54, 95],
    ]);
  });

  it("puts a clicked temperature in the limit that has focus", () => {
    renderDialog();
    const low = peakRow("71.3").getByLabelText("Low (°C)");
    fireEvent.focus(low);
    clickTrace(58.26);
    expect(low).toHaveValue(58.3);
    expect(screen.queryByRole("button", { name: "Add a peak here" })).not.toBeInTheDocument();
    // Once the field is left, a click is a spot again.
    fireEvent.blur(low);
    clickTrace(45.1);
    expect(low).toHaveValue(58.3);
    expect(screen.getByRole("button", { name: "Add a peak here" })).toBeInTheDocument();
  });

  it("offers to add a peak where the trace has none, and gives it a row", async () => {
    const added = step("p7", "r1", 45.12, { source: "manual" });
    const view = renderDialog();
    clickTrace(71.3);
    expect(screen.queryByRole("button", { name: "Add a peak here" })).not.toBeInTheDocument();
    clickTrace(45.123);
    expect(customInstance).not.toHaveBeenCalled();
    customInstance.mockResolvedValue({ step: added, recalculated: true, compute_warning: null });
    fireEvent.click(screen.getByRole("button", { name: "Add a peak here" }));
    await waitFor(() =>
      expect(customInstance).toHaveBeenCalledWith({
        url: "/api/v1/runs/run1/melting-steps",
        method: "POST",
        data: { well_id: "r1", channel_key: "a", value: 45.12 },
      }),
    );
    await waitFor(() =>
      expect(screen.queryByRole("button", { name: "Add a peak here" })).not.toBeInTheDocument(),
    );
    // The page reloads the analysis; the new peak has a row and the ranges follow.
    view.rerender(dialog({ analysis: analysisOf({ steps: [...STEPS, added] }) }));
    expect(rowNames()).toEqual(["Peak at 36.6 °C", "Peak at 45.12 °C", "Peak at 71.3 °C"]);
    expect(peakRow("45.12").getByText("Placed by hand")).toBeInTheDocument();
    expect(peakRow("36.6").getByLabelText("High (°C)")).toHaveValue(40.9);
  });

  it("shows the server's sentence when the peak cannot be added", async () => {
    customInstance.mockRejectedValueOnce(
      new ApiError("API error: 409", 409, { message: "The run is locked." }),
    );
    renderDialog();
    clickTrace(45);
    fireEvent.click(screen.getByRole("button", { name: "Add a peak here" }));
    expect(await screen.findByText("The run is locked.")).toBeInTheDocument();
  });

  it("does not offer a peak on a run that cannot be recalculated", () => {
    renderDialog({ canRecalculate: false });
    clickTrace(45);
    expect(screen.queryByRole("button", { name: "Add a peak here" })).not.toBeInTheDocument();
  });

  it("adds a window without a peak as an empty row", () => {
    renderDialog();
    fireEvent.click(screen.getByRole("button", { name: "Add a transition without a peak" }));
    const [row] = freeRows();
    expect(within(row).getByLabelText("Name")).toHaveValue("");
    expect(within(row).getByLabelText("Low (°C)")).toHaveValue(null);
    expect(within(row).getByLabelText("High (°C)")).toHaveValue(null);
    expect(bands()).toHaveLength(2);
  });

  it("says when the run has no reference, and still saves a typed window", async () => {
    renderDialog({
      run: { ...RUN, positions: RUN.positions.filter((p) => p.well_type !== "reference") },
      analysis: analysisOf({ windows: [win("Main", 50, 85)] }),
    });
    expect(
      screen.getByText(
        "This run has no reference position. Mark one in Edit labeling, or add a transition by typing its range.",
      ),
    ).toBeInTheDocument();
    expect(within(existing()).getByText("Main 50–85 °C")).toBeInTheDocument();
    expect(screen.queryByTestId("plot")).not.toBeInTheDocument();
    expect(screen.queryByRole("group")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Add a transition without a peak" }));
    const row = within(freeRows()[0]);
    type(row, "Name", "Low");
    type(row, "Low (°C)", "30");
    expect(save()).toBeDisabled();
    type(row, "High (°C)", "45");
    fireEvent.click(save());
    await waitFor(() => expect(requests("/temperature-windows")).toHaveLength(1));
    expect(requests("/temperature-windows")[0].data).toEqual({
      window: "Low",
      channel_key: "a",
      low: 30,
      high: 45,
      measures: ["tm", "delta_tm"],
    });
  });

  it("says when the reference has no peak on the signal, and a click on its trace offers one", () => {
    renderDialog({ analysis: analysisOf({ steps: [] }) });
    expect(
      screen.getByText(
        "The reference has no peak on this signal. Click its trace to add one, or add a transition by typing its range.",
      ),
    ).toBeInTheDocument();
    expect(screen.queryByRole("group")).not.toBeInTheDocument();
    clickTrace(55);
    expect(screen.getByRole("button", { name: "Add a peak here" })).toBeInTheDocument();
  });

  it("does not send a named row whose low is not below its high", () => {
    renderDialog();
    const row = peakRow("36.6");
    type(row, "Name", "Low");
    expect(save()).toBeEnabled();
    type(row, "Low (°C)", "60");
    expect(row.getByText("Low must be below High.")).toBeInTheDocument();
    expect(save()).toBeDisabled();
  });

  it("saves one window per named row, in row order, then recalculates the run and closes", async () => {
    render(<Closing />, { wrapper });
    type(peakRow("71.3"), "Name", " Main ");
    fireEvent.click(peakRow("71.3").getByLabelText("ΔTm"));
    fireEvent.click(screen.getByRole("button", { name: "Add a transition without a peak" }));
    const free = within(freeRows()[0]);
    type(free, "Name", "Late");
    type(free, "Low (°C)", "95");
    type(free, "High (°C)", "99.5");
    fireEvent.click(save());
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(onOpenChange).toHaveBeenCalledWith(false);
    // The recalculation outlives the dialog.
    await waitFor(() => expect(requests("/recompute")).toHaveLength(1));
    // The unnamed peak at 36.6 creates nothing.
    expect(requests("/temperature-windows")).toEqual([
      {
        url: "/api/v1/protocols/p1/temperature-windows",
        method: "POST",
        data: { window: "Main", channel_key: "a", low: 54, high: 95, measures: ["tm"] },
      },
      {
        url: "/api/v1/protocols/p1/temperature-windows",
        method: "POST",
        data: {
          window: "Late",
          channel_key: "a",
          low: 95,
          high: 99.5,
          measures: ["tm", "delta_tm"],
        },
      },
    ]);
    expect(customInstance).toHaveBeenLastCalledWith({
      url: "/api/v1/runs/run1/recompute",
      method: "POST",
    });
    // The page's protocol and analysis are read again.
    expect(qc.getQueryState(PROTOCOL_KEY)?.isInvalidated).toBe(true);
    expect(qc.getQueryState(ANALYSIS_KEY)?.isInvalidated).toBe(true);
  });

  it("keeps the saved window and the failed row with the server's sentence when the second fails", async () => {
    customInstance.mockReset();
    customInstance
      .mockResolvedValueOnce({})
      .mockRejectedValueOnce(
        new ApiError("API error: 409", 409, {
          message: "A readout named 'Tm (Main)' already exists",
        }),
      )
      .mockResolvedValue({});
    renderDialog();
    type(peakRow("36.6"), "Name", "Main");
    type(peakRow("71.3"), "Name", "Main");
    fireEvent.click(save());
    const failed = peakRow("71.3");
    expect(await failed.findByText("A readout named 'Tm (Main)' already exists")).toBeVisible();
    expect(requests("/temperature-windows")).toHaveLength(2);
    // The first is a window now, and its peak has no row; the failed row is as typed.
    expect(within(existing()).getByText("Main 25–54 °C")).toBeInTheDocument();
    expect(rowNames()).toEqual(["Peak at 71.3 °C"]);
    expect(failed.getByLabelText("Name")).toHaveValue("Main");
    expect(onOpenChange).not.toHaveBeenCalled();
    // One window was saved, so the run's stored readouts follow.
    await waitFor(() => expect(requests("/recompute")).toHaveLength(1));
    expect(qc.getQueryState(ANALYSIS_KEY)?.isInvalidated).toBe(true);
    // Typing in the row clears the sentence.
    type(failed, "Name", "Second");
    expect(
      screen.queryByText("A readout named 'Tm (Main)' already exists"),
    ).not.toBeInTheDocument();
  });

  it("stops at the row that failed", async () => {
    customInstance.mockReset();
    customInstance.mockRejectedValue(
      new ApiError("API error: 409", 409, { message: "The protocol is locked." }),
    );
    renderDialog();
    type(peakRow("36.6"), "Name", "Low");
    type(peakRow("71.3"), "Name", "Main");
    fireEvent.click(save());
    expect(await peakRow("36.6").findByText("The protocol is locked.")).toBeVisible();
    expect(customInstance).toHaveBeenCalledTimes(1);
    expect(save()).toBeEnabled();
  });

  it("says the stored results stay when the run is approved or locked, and does not recalculate", async () => {
    renderDialog({ canRecalculate: false });
    type(peakRow("71.3"), "Name", "Main");
    fireEvent.click(save());
    expect(
      await screen.findByText(
        "This run is approved (or locked), so its stored results do not change. The new transitions apply to later runs; the values shown here are for viewing.",
      ),
    ).toBeInTheDocument();
    expect(within(existing()).getByText("Main 54–95 °C")).toBeInTheDocument();
    expect(requests("/recompute")).toHaveLength(0);
    expect(customInstance).toHaveBeenCalledTimes(1);
    expect(onOpenChange).not.toHaveBeenCalled();
    expect(qc.getQueryState(ANALYSIS_KEY)?.isInvalidated).toBe(true);
    // Nothing is left to cancel.
    expect(screen.getByRole("button", { name: "Done" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Cancel" })).not.toBeInTheDocument();
  });

  it("starts from the proposal at each opening", () => {
    const view = renderDialog();
    type(peakRow("36.6"), "Name", "Low");
    view.rerender(<NamePeaksDialog {...dialog().props} open={false} />);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    view.rerender(dialog());
    expect(peakRow("36.6").getByLabelText("Name")).toHaveValue("");
  });
});
