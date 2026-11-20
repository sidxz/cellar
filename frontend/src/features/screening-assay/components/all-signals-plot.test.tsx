import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { MeltingAnalysis, RunCurves } from "../types";

interface PlotProps {
  data: Array<Record<string, unknown>>;
  layout: {
    shapes: { type: string; x0: number; x1: number; line: { dash?: string } }[];
    xaxis: { range?: number[]; title: { text: string }; showticklabels?: boolean };
    yaxis: { uirevision: string };
  };
  onClick?: (ev: unknown) => void;
  onHover?: (ev: unknown) => void;
  onUnhover?: () => void;
  onRelayout?: (ev: unknown) => void;
}
/** What each plot on screen was last drawn with, by its element. */
const plots = new WeakMap<Element, PlotProps>();
vi.mock("@/shared/lib/plotly", () => ({
  Plot: (props: PlotProps) => (
    <div
      data-testid="plot"
      ref={(el) => {
        if (el) plots.set(el, props);
      }}
    />
  ),
  getPlotlyGlobal: () => undefined,
}));

// The curves are read for real, through one query cache; only the request is stubbed.
interface Asked {
  url: string;
  params: { channel?: string; view?: string; window?: number };
}
const customInstance = vi.fn();
vi.mock("@/shared/lib/api/custom-instance", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/shared/lib/api/custom-instance")>()),
  customInstance: (args: unknown) => customInstance(args),
}));

const melting: { data?: MeltingAnalysis } = {};
const found: { data?: unknown } = {};
const saveStep = vi.fn();
vi.mock("../hooks/use-melting-analysis", () => ({
  useMeltingAnalysis: () => ({ ...melting, isLoading: false, refetch: vi.fn() }),
  usePeakCandidates: (_runId: string, wellId: string | undefined) => ({
    data: wellId ? found.data : undefined,
  }),
  useAddMeltingStep: () => ({ mutate: saveStep, isPending: false }),
  useReviewMeltingStep: () => ({ mutate: saveStep, isPending: false }),
  useAssignMeltingStep: () => ({ mutate: saveStep, isPending: false }),
  useAcceptMeltingSteps: () => ({ mutate: saveStep, isPending: false, isError: false }),
}));
vi.mock("@/shared/components/data-grid/data-grid", async () => ({
  DataGrid: (await import("../test/test-data-grid")).TableGrid,
}));
vi.mock("@/shared/hooks/use-current-user", () => ({ useCanEdit: () => true }));
vi.mock("@/shared/components/export/export-toolbar", () => ({ ExportToolbar: () => null }));
vi.mock("@/shared/hooks/use-workspace-members", () => ({
  useWorkspaceMembers: () => ({ data: [] }),
}));
vi.mock("./edit-labelling-dialog", () => ({ EditLabellingDialog: () => null }));
vi.mock("./name-peaks-dialog", () => ({ NamePeaksDialog: () => null }));
vi.mock("../hooks/use-protocols", () => ({
  useProtocol: () => ({
    data: { id: "p1", recommended_hit_criteria: null, readout_definitions: [] },
  }),
}));
vi.mock("../hooks/use-runs", () => ({
  useSetRunHitCriteria: () => ({ mutate: vi.fn(), isPending: false }),
  useResetRunHitCriteria: () => ({ mutate: vi.fn(), isPending: false }),
}));
vi.mock("@/shared/components/entity-name", () => ({
  MemberName: ({ id }: { id: string }) => <span>{id}</span>,
}));

import { RunCurvesPanel } from "./run-curves-panel";

const QUIET = "To pick or edit a peak on the plot, choose one signal.";
const FAILED = "Could not load the traces. Reload the page and try again.";
const CURVES_URL = "/api/v1/runs/r1/curves";

const positions = Array.from({ length: 3 }, (_, i) => ({
  well_id: `w${i + 1}`,
  position: `A${i + 1}`,
  row: "A",
  column: i + 1,
  well_type: i === 0 ? "reference" : "sample",
  registration_number: null,
  position_label: `Position ${i + 1}`,
  label: i === 0 ? "Protein alone" : `ABC-000000${i + 1}`,
  note: null,
  dose: i === 0 ? null : 50,
}));
const SIGNALS = [
  { key: "a", label: "Signal A", x_unit: "°C", y_unit: null, x_label: null },
  { key: "b", label: "Signal B", x_unit: "°C", y_unit: null, x_label: null },
];
let signals = SIGNALS;

/** The run's curves for a signal and view; signal a spans 20–95 °C, signal b 25–90 °C. */
function curvesOf({ params }: Asked): RunCurves {
  const channel = params.channel ?? "a";
  const view = params.view ?? "measured";
  return {
    run_id: "r1",
    dose_unit: "uM",
    holder: { kind: "cassette", rows: 1, columns: 3, label: "Holder of 3" },
    positions,
    channels: signals,
    channel,
    view,
    window: view === "derivative" ? (params.window ?? 3.5) : null,
    curves: positions.map((p) => ({
      well_id: p.well_id,
      x: channel === "a" ? [20, 50, 95] : [25, 50, 90],
      y: view === "derivative" ? [0, 1, 0] : [1, 2, 3],
      reported: [],
    })),
  };
}

const RUN = {
  id: "r1",
  protocol_id: "p1",
  run_date: "2026-11-13",
  operator: "u1",
  status: "draft",
  is_locked: false,
  hit_criteria: null,
  hit_criteria_set_by: null,
  hit_criteria_set_at: null,
} as const;

/** "Main" on both signals: 30–90 °C on a, 40–70 °C on b. Position 2 has no
 *  peak in it on signal a (so it is the one selected first), and one on b. */
function analysis(): MeltingAnalysis {
  const win = (channel_key: string, low: number, high: number) => ({
    window: "Main",
    channel_key,
    low,
    high,
    tm_readout_id: null,
    delta_tm_readout_id: null,
    reference_tm: 60,
    reference_count: 1,
    flags: [],
    series: [],
    positions: positions.map((p) => ({
      well_id: p.well_id,
      tm: p.well_id === "w1" ? 60 : p.well_id === "w3" ? 68 : null,
      delta_tm: p.well_id === "w1" ? 0 : p.well_id === "w3" ? 8 : null,
      flags: p.well_id === "w2" ? ["no_step_in_window"] : [],
      named_by: p.well_id === "w2" ? null : "range",
      step_id: p.well_id === "w2" ? null : `${channel_key}-${p.well_id}`,
    })),
  });
  const step = (
    id: string,
    well_id: string,
    channel_key: string,
    value: number,
    status: string,
  ) => ({
    id,
    well_id,
    channel_key,
    source: "instrument",
    value,
    instrument_value: value,
    instrument_label: null,
    status,
    reason: null,
    changed_by: null,
    changed_at: null,
    assigned_window: null,
    assignment_reason: null,
    assigned_by: null,
    assigned_at: null,
    version: 3,
  });
  return {
    run_id: "r1",
    edit_refusal: null,
    steps: [
      step("a-w1", "w1", "a", 60, "accepted"),
      step("a-w3", "w3", "a", 68, "unreviewed"),
      step("b-w1", "w1", "b", 52, "unreviewed"),
      step("b-w2", "w2", "b", 55, "accepted"),
    ],
    windows: [win("a", 30, 90), win("b", 40, 70)],
    step_checks: [],
    outside_every_window: [],
  } as MeltingAnalysis;
}

function show() {
  // As the application's client: what was read is not read again at once.
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: 60_000 } },
  });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
  return render(<RunCurvesPanel runId="r1" run={RUN} />, { wrapper });
}

const viewTab = (name: string) => screen.getByRole("tab", { name });
const stack = () => screen.getByRole("region", { name: "All signals" });
const panels = () => within(stack()).getAllByRole("figure");
const captions = () => panels().map((f) => f.querySelector("figcaption")?.textContent);
const panel = (caption: string) => {
  const figure = panels().find((f) => f.querySelector("figcaption")?.textContent === caption);
  if (!figure) throw new Error(`no panel ${caption}`);
  return figure;
};
const drawn = (el: Element) => {
  const props = plots.get(el);
  if (!props) throw new Error("plot not drawn");
  return props;
};
const plotOf = (caption: string) => drawn(within(panel(caption)).getByTestId("plot"));
const everyPlot = () => within(stack()).getAllByTestId("plot").map(drawn);

/** The single view, once its curves are in. */
async function showSingle() {
  show();
  await screen.findByTestId("plot");
}

/** The all-signals view, once every panel is drawn. */
async function showAll(drawnPanels = 4) {
  await showSingle();
  fireEvent.mouseDown(viewTab("All signals"));
  await waitFor(() => expect(within(stack()).getAllByTestId("plot")).toHaveLength(drawnPanels));
}

/** Each curves request so far: signal ("first" while none is named), view, smoothing. */
const asked = () =>
  customInstance.mock.calls
    .map(([a]) => a as Asked)
    .filter((a) => a.url === CURVES_URL)
    .map((a) =>
      [a.params.channel ?? "first", a.params.view, a.params.window].filter(Boolean).join("/"),
    );

beforeEach(() => {
  Element.prototype.scrollIntoView = vi.fn();
  signals = SIGNALS;
  melting.data = analysis();
  found.data = undefined;
  saveStep.mockReset();
  customInstance.mockReset();
  customInstance.mockImplementation((a: Asked) =>
    a.url === CURVES_URL ? Promise.resolve(curvesOf(a)) : Promise.reject(new Error(a.url)),
  );
});

describe("All signals view", () => {
  it("is offered by the view switch, never by the Signal dropdown", async () => {
    await showSingle();
    const views = within(screen.getByRole("tablist", { name: "View" })).getAllByRole("tab");
    expect(views.map((t) => t.textContent)).toEqual(["Measured", "Derivative", "All signals"]);
    fireEvent.keyDown(screen.getByRole("combobox", { name: "Signal" }), { key: "Enter" });
    expect(screen.getAllByRole("option").map((o) => o.textContent)).toEqual([
      "Signal A",
      "Signal B",
    ]);
  });

  it("is not offered on a run with one signal", async () => {
    signals = SIGNALS.slice(0, 1);
    await showSingle();
    const views = within(screen.getByRole("tablist", { name: "View" })).getAllByRole("tab");
    expect(views.map((t) => t.textContent)).toEqual(["Measured", "Derivative"]);
  });

  it("asks for each signal's measured and derivative curves once and stacks two labeled panels per signal", async () => {
    await showSingle();
    expect(asked()).toEqual(["first/measured"]);
    fireEvent.mouseDown(viewTab("All signals"));
    expect(viewTab("All signals")).toHaveAttribute("aria-selected", "true");
    await waitFor(() => expect(within(stack()).getAllByTestId("plot")).toHaveLength(4));
    // The derivative over the measured trace, signal by signal in the dropdown's order.
    expect(captions()).toEqual(["Signal A · d/dT", "Signal A", "Signal B · d/dT", "Signal B"]);
    for (const [caption, view, x] of [
      ["Signal A · d/dT", "derivative", [20, 50, 95]],
      ["Signal A", "measured", [20, 50, 95]],
      ["Signal B · d/dT", "derivative", [25, 50, 90]],
      ["Signal B", "measured", [25, 50, 90]],
    ] as const) {
      // The selected sample and, with the reference switch on, the reference.
      expect(plotOf(caption).data.map((t) => t.meta)).toEqual(["w1", "w2"]);
      expect(plotOf(caption).data[0].x).toEqual(x);
      expect(plotOf(caption).data[0].y).toEqual(view === "derivative" ? [0, 1, 0] : [1, 2, 3]);
    }
    // The shown signal's measured curves were already read by the single view.
    expect(asked().sort()).toEqual([
      "b/derivative",
      "b/measured",
      "first/derivative",
      "first/measured",
    ]);
  });

  it("shows the loading state until every request has answered", async () => {
    await showSingle();
    let answer: (curves: RunCurves) => void = () => {};
    customInstance.mockImplementation((a: Asked) =>
      a.params.channel === "b" && a.params.view === "derivative"
        ? new Promise<RunCurves>((resolve) => {
            answer = () => resolve(curvesOf(a));
          })
        : Promise.resolve(curvesOf(a)),
    );
    fireEvent.mouseDown(viewTab("All signals"));
    await waitFor(() => expect(asked()).toHaveLength(4));
    expect(screen.queryByTestId("plot")).toBeNull();
    expect(screen.getByTestId("all-signals-loading")).toBeInTheDocument();
    await act(async () => answer(curvesOf({ url: CURVES_URL, params: {} })));
    await waitFor(() => expect(within(stack()).getAllByTestId("plot")).toHaveLength(4));
  });

  it("shows one temperature range on every panel; only the bottom one titles and numbers the axis", async () => {
    await showAll();
    // All that the drawn traces of any signal cover.
    expect(everyPlot().map((p) => p.layout.xaxis.range)).toEqual(Array(4).fill([20, 95]));
    const [bottom, ...above] = everyPlot().reverse();
    expect(bottom.layout.xaxis.title.text).toBe("°C");
    expect(bottom.layout.xaxis.showticklabels).not.toBe(false);
    for (const p of above) {
      expect(p.layout.xaxis.title.text).toBe("");
      expect(p.layout.xaxis.showticklabels).toBe(false);
    }
  });

  it("a zoom or pan on one panel reaches every panel, and a reset on any shows all again", async () => {
    await showAll();
    const before = everyPlot().map((p) => p.layout.yaxis.uirevision);
    act(() => plotOf("Signal B").onRelayout?.({ "xaxis.range[0]": 46, "xaxis.range[1]": 51 }));
    expect(everyPlot().map((p) => p.layout.xaxis.range)).toEqual(Array(4).fill([46, 51]));
    // A zoom of one panel's own y axis is that panel's.
    act(() => plotOf("Signal A").onRelayout?.({ "yaxis.range[0]": 0, "yaxis.range[1]": 1 }));
    expect(everyPlot().map((p) => p.layout.xaxis.range)).toEqual(Array(4).fill([46, 51]));
    expect(everyPlot().map((p) => p.layout.yaxis.uirevision)).toEqual(before);
    act(() =>
      plotOf("Signal A · d/dT").onRelayout?.({ "xaxis.autorange": true, "yaxis.autorange": true }),
    );
    expect(everyPlot().map((p) => p.layout.xaxis.range)).toEqual(Array(4).fill([20, 95]));
    // Every panel's y axis is drawn anew, so a zoom left on another panel goes too.
    const after = everyPlot().map((p) => p.layout.yaxis.uirevision);
    for (const [i, revision] of after.entries()) expect(revision).not.toBe(before[i]);
  });

  it("draws on each panel its own signal's peaks and transition band, as the single view does", async () => {
    await showAll();
    const marks = (caption: string) => {
      const shapes = plotOf(caption).layout.shapes;
      return {
        bands: shapes.filter((s) => s.type === "rect").map((s) => [s.x0, s.x1]),
        peaks: shapes.filter((s) => s.type === "line").map((s) => [s.x0, s.line.dash]),
      };
    };
    for (const caption of ["Signal A · d/dT", "Signal A"])
      expect(marks(caption)).toEqual({ bands: [[30, 90]], peaks: [[60, "solid"]] });
    for (const caption of ["Signal B · d/dT", "Signal B"])
      expect(marks(caption)).toEqual({
        bands: [[40, 70]],
        peaks: [
          [52, "dash"],
          [55, "solid"],
        ],
      });
    // Turning the reference traces off takes the reference from every panel.
    fireEvent.click(screen.getByRole("switch", { name: "Reference traces" }));
    for (const p of everyPlot()) expect(p.data.map((t) => t.meta)).toEqual(["w2"]);
  });

  it("the trace under the pointer is drawn thicker on its own panel only", async () => {
    await showAll();
    const widths = () =>
      everyPlot().map(
        (p) => (p.data.find((t) => t.meta === "w2")?.line as { width: number }).width,
      );
    const resting = widths();
    act(() => plotOf("Signal A").onHover?.({ points: [{ data: { meta: "w2" } }] }));
    expect(widths()).toEqual([resting[0], 3, resting[2], resting[3]]);
    act(() => plotOf("Signal A").onUnhover?.());
    expect(widths()).toEqual(resting);
  });

  it("applies Display to every panel and leaves the image export to the single views", async () => {
    await showSingle();
    const openDisplay = () => fireEvent.click(screen.getByRole("button", { name: "Display" }));
    openDisplay();
    expect(screen.getByRole("button", { name: "PNG" })).toBeInTheDocument();
    fireEvent.mouseDown(viewTab("All signals"));
    await waitFor(() => expect(within(stack()).getAllByTestId("plot")).toHaveLength(4));
    expect(screen.queryByRole("button", { name: "PNG" })).toBeNull();
    for (const p of everyPlot()) expect(p.layout.shapes.some((s) => s.type === "line")).toBe(true);
    fireEvent.mouseDown(screen.getByRole("tab", { name: "Off" }));
    for (const p of everyPlot()) expect(p.layout.shapes.some((s) => s.type === "line")).toBe(false);
  });

  it("leaves the dropdown, the summary, the selected sample and the table as they were", async () => {
    await showSingle();
    const read = () => ({
      signal: screen.getByRole("combobox", { name: "Signal" }).textContent,
      summary: screen.getByRole("region", { name: "Thermal analysis summary" }).textContent,
      sample: screen.getByLabelText("Selected sample").textContent,
      table: screen.getAllByRole("table")[0].textContent,
      peaks: screen.getByRole("button", { name: "Next unreviewed" }).closest("section")
        ?.textContent,
    });
    const before = read();
    expect(before.signal).toBe("Signal A");
    fireEvent.mouseDown(viewTab("All signals"));
    await waitFor(() => expect(within(stack()).getAllByTestId("plot")).toHaveLength(4));
    expect(read()).toEqual(before);
  });

  it("offers no picking: a pick is dropped, a click does nothing and one line says where to pick", async () => {
    await showSingle();
    act(() =>
      drawn(screen.getByTestId("plot")).onClick?.({
        points: [{ x: 52.3, y: 1, data: { meta: "w2" } }],
      }),
    );
    expect(screen.getByRole("region", { name: "Spot picked" })).toBeInTheDocument();
    expect(screen.queryByText(QUIET)).toBeNull();
    fireEvent.mouseDown(viewTab("All signals"));
    await waitFor(() => expect(within(stack()).getAllByTestId("plot")).toHaveLength(4));
    expect(screen.queryByRole("region", { name: /picked$/ })).toBeNull();
    for (const p of everyPlot()) expect(p.onClick).toBeUndefined();
    expect(screen.getByText(QUIET)).toBeInTheDocument();
  });

  it("Show <signal> under the peaks returns to the Measured view of that signal", async () => {
    found.data = {
      signals: [
        { channel_key: "a", candidates: [] },
        { channel_key: "b", candidates: [{ value: 55.2, direction: "up", strength: 3 }] },
      ],
    };
    await showSingle();
    // Entered from the Derivative view: leaving by a signal still lands on Measured.
    fireEvent.mouseDown(viewTab("Derivative"));
    fireEvent.mouseDown(viewTab("All signals"));
    await waitFor(() => expect(within(stack()).getAllByTestId("plot")).toHaveLength(4));
    const requests = asked().length;
    fireEvent.click(screen.getByRole("button", { name: "Show Signal B" }));
    await waitFor(() => expect(screen.queryByRole("region", { name: "All signals" })).toBeNull());
    expect(viewTab("Measured")).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("combobox", { name: "Signal" })).toHaveTextContent("Signal B");
    await waitFor(() => expect(drawn(screen.getByTestId("plot")).data[0].x).toEqual([25, 50, 90]));
    expect(drawn(screen.getByTestId("plot")).data[0].y).toEqual([1, 2, 3]);
    expect(screen.queryByLabelText("Smoothing window")).toBeNull();
    // Its measured curves were read for its panel.
    expect(asked()).toHaveLength(requests);
  });

  it("choosing a signal in the dropdown does the same", async () => {
    await showAll();
    fireEvent.keyDown(screen.getByRole("combobox", { name: "Signal" }), { key: "Enter" });
    fireEvent.click(screen.getByRole("option", { name: "Signal B" }));
    await waitFor(() => expect(screen.queryByRole("region", { name: "All signals" })).toBeNull());
    expect(viewTab("Measured")).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("combobox", { name: "Signal" })).toHaveTextContent("Signal B");
    await waitFor(() => expect(drawn(screen.getByTestId("plot")).data[0].x).toEqual([25, 50, 90]));
    expect(asked()).toHaveLength(4);
  });

  it("choosing Measured or Derivative returns to the single plot", async () => {
    await showAll();
    fireEvent.mouseDown(viewTab("Derivative"));
    expect(screen.queryByRole("region", { name: "All signals" })).toBeNull();
    expect(viewTab("Derivative")).toHaveAttribute("aria-selected", "true");
    expect(drawn(screen.getByTestId("plot")).data[0].y).toEqual([0, 1, 0]);
    expect(drawn(screen.getByTestId("plot")).onClick).toBeDefined();
    fireEvent.mouseDown(viewTab("All signals"));
    await waitFor(() => expect(within(stack()).getAllByTestId("plot")).toHaveLength(4));
    fireEvent.mouseDown(viewTab("Measured"));
    expect(screen.queryByRole("region", { name: "All signals" })).toBeNull();
    expect(drawn(screen.getByTestId("plot")).data[0].y).toEqual([1, 2, 3]);
    // Nothing was asked for twice.
    expect(asked()).toHaveLength(4);
  });

  it("a failed request says so in its panel and the others still draw", async () => {
    customInstance.mockImplementation((a: Asked) =>
      a.params.channel === "b" && a.params.view === "derivative"
        ? Promise.reject(new Error("boom"))
        : Promise.resolve(curvesOf(a)),
    );
    await showAll(3);
    expect(captions()).toEqual(["Signal A · d/dT", "Signal A", "Signal B · d/dT", "Signal B"]);
    expect(within(panel("Signal B · d/dT")).getByText(FAILED)).toBeInTheDocument();
    expect(within(panel("Signal B · d/dT")).queryByTestId("plot")).toBeNull();
    expect(screen.getAllByText(FAILED)).toHaveLength(1);
    for (const caption of ["Signal A · d/dT", "Signal A", "Signal B"])
      expect(plotOf(caption).data.map((t) => t.meta)).toEqual(["w1", "w2"]);
  });

  it("when the single view's own request had failed, its panel says so and the key stays", async () => {
    customInstance.mockImplementation((a: Asked) =>
      !a.params.channel && a.params.view === "derivative"
        ? Promise.reject(new Error("boom"))
        : Promise.resolve(curvesOf(a)),
    );
    await showSingle();
    fireEvent.mouseDown(viewTab("Derivative"));
    expect(await screen.findByText(FAILED)).toBeInTheDocument();
    fireEvent.mouseDown(viewTab("All signals"));
    await waitFor(() => expect(within(stack()).getAllByTestId("plot")).toHaveLength(3));
    expect(within(panel("Signal A · d/dT")).getByText(FAILED)).toBeInTheDocument();
    expect(screen.getAllByText(FAILED)).toHaveLength(1);
    expect(screen.getByTestId("curve-key")).toHaveTextContent("Reference");
  });

  it("shows the Derivative view's smoothing, and a new one asks again for the derivatives only", async () => {
    await showAll();
    // The default the API used, as the Derivative view shows it.
    expect(screen.getByLabelText("Smoothing window")).toHaveValue(3.5);
    fireEvent.change(screen.getByLabelText("Smoothing window"), { target: { value: "2" } });
    fireEvent.blur(screen.getByLabelText("Smoothing window"));
    await waitFor(() => expect(asked()).toHaveLength(6));
    expect(asked().slice(4).sort()).toEqual(["b/derivative/2", "first/derivative/2"]);
    await waitFor(() => expect(screen.getByLabelText("Smoothing window")).toHaveValue(2));
    // The Derivative view then uses the same smoothing, already read.
    fireEvent.mouseDown(viewTab("Derivative"));
    expect(screen.getByLabelText("Smoothing window")).toHaveValue(2);
    expect(asked()).toHaveLength(6);
  });
});
