import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { MEASURED_CURVE_COLORS } from "@/shared/lib/chart-colors";
import type { HitCriterion, MeltWindowPosition, MeltingAnalysis, RunCurves } from "../types";

const plotCalls: Array<{
  data: Array<Record<string, unknown>>;
  layout: Record<string, unknown>;
  style?: { height?: number };
  onClick?: (ev: unknown) => void;
  onRelayout?: (ev: unknown) => void;
}> = [];
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
/** One spy for the three saves: add, review and assign. */
const saveStep = vi.fn();
vi.mock("../hooks/use-melting-analysis", () => ({
  useMeltingAnalysis: () => ({ ...melting, refetch: vi.fn() }),
  // The peaks found in a position's traces are covered in melting-steps-panel.test.tsx.
  usePeakCandidates: () => ({ data: undefined }),
  useAddMeltingStep: () => ({ mutate: saveStep, isPending: false }),
  useReviewMeltingStep: () => ({ mutate: saveStep, isPending: false }),
  useAssignMeltingStep: () => ({ mutate: saveStep, isPending: false }),
  useAcceptMeltingSteps: () => ({ mutate: saveStep, isPending: false, isError: false }),
}));
vi.mock("@/shared/components/data-grid/data-grid", async () => ({
  DataGrid: (await import("../test/test-data-grid")).TableGrid,
}));

const canEdit = { value: true };
vi.mock("@/shared/hooks/use-current-user", () => ({ useCanEdit: () => canEdit.value }));
// The run's export: the toolbar stands in as one button that builds a PDF request.
const exported: { formats?: readonly string[]; request?: unknown }[] = [];
vi.mock("@/shared/components/export/export-toolbar", () => ({
  ExportToolbar: ({
    formats,
    buildRequest,
  }: {
    formats?: readonly string[];
    buildRequest: (f: string) => unknown;
  }) => (
    <button type="button" onClick={() => exported.push({ formats, request: buildRequest("pdf") })}>
      Export
    </button>
  ),
}));
vi.mock("@/shared/hooks/use-workspace-members", () => ({
  useWorkspaceMembers: () => ({
    data: [
      { user_id: "u1", name: "Ada Lovelace", email: "ada@lab.org" },
      { user_id: "u2", name: "", email: "grace@lab.org" },
      { user_id: "u3", name: "Mary Anning", email: "mary@lab.org" },
    ],
  }),
}));
vi.mock("./edit-labelling-dialog", () => ({
  EditLabellingDialog: ({ open }: { open: boolean }) =>
    open ? <div data-testid="edit-labelling">edit labelling dialog</div> : null,
}));

// The naming dialog is covered in name-peaks-dialog.test.tsx; here, what it is given.
const naming: { open: boolean; canRecalculate: boolean; set: { curves: Map<string, unknown> } }[] =
  [];
vi.mock("./name-peaks-dialog", () => ({
  NamePeaksDialog: (props: (typeof naming)[number]) => {
    naming.push(props);
    return props.open ? <div data-testid="name-peaks" /> : null;
  },
}));

const protocolData: { value: unknown } = { value: undefined };
vi.mock("../hooks/use-protocols", () => ({
  useProtocol: () => ({ data: protocolData.value }),
}));
const setHitCriteria = vi.fn();
vi.mock("../hooks/use-runs", () => ({
  useSetRunHitCriteria: () => ({ mutate: setHitCriteria, isPending: false }),
  useResetRunHitCriteria: () => ({ mutate: vi.fn(), isPending: false }),
}));
vi.mock("@/shared/components/entity-name", () => ({
  MemberName: ({ id }: { id: string }) => <span>{id}</span>,
}));

import { gridRow } from "../test/test-data-grid";
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
const OUTSIDE: HitCriterion = {
  readout_name: "ΔTm (Main)",
  operator: "not_between",
  value: [-2, 2],
};
/** The run with "ΔTm (Main) outside −2 to 2" recorded. */
const RULE_RUN = {
  ...RUN,
  hit_criteria: [OUTSIDE],
  hit_criteria_set_by: "u1",
  hit_criteria_set_at: "2026-11-13",
};
const PROTOCOL = {
  id: "p1",
  recommended_hit_criteria: [OUTSIDE],
  readout_definitions: [
    {
      name: "ΔTm (Main)",
      melt_config: { window: "Main", measure: "delta_tm", channel_key: "a", low: 30, high: 90 },
    },
  ],
};

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
    series: [],
    positions: positions.map((p) => ({
      well_id: p.well_id,
      tm: null,
      delta_tm: null,
      flags: [],
      named_by: null,
      step_id: null,
      ...cells[p.well_id],
    })),
  });
  melting.data = {
    run_id: "r1",
    edit_refusal: null,
    steps: [],
    windows: windows ? [win("Main")] : [],
    step_checks: [],
    outside_every_window: [],
  };
}

const selectedRows = () =>
  [...document.querySelectorAll("tr[data-row-id]")]
    .filter((tr) => tr.className.includes("bg-primary/10"))
    .map((tr) => tr.getAttribute("data-row-id"));

/** The run tab keeps Markers, Color and Export behind the Display button. */
const openDisplay = () => fireEvent.click(screen.getByRole("button", { name: "Display" }));

function choose(name: string, option: string) {
  fireEvent.keyDown(screen.getByRole("combobox", { name }), { key: "Enter" });
  fireEvent.click(screen.getByRole("option", { name: option }));
}

function analysisSetting(name: string) {
  fireEvent.keyDown(screen.getByRole("button", { name: "Analysis settings" }), { key: "Enter" });
  fireEvent.click(screen.getByRole("menuitem", { name }));
}

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
  Element.prototype.scrollIntoView = vi.fn();
  canEdit.value = true;
  protocolData.value = PROTOCOL;
  setHitCriteria.mockReset();
  saveStep.mockReset();
  melting.data = undefined;
  melting.isLoading = false;
  naming.length = 0;
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
    // Without an analysis (it failed), the results column says so.
    expect(
      screen.getByText("Could not load the analysis. Reload the page and try again."),
    ).toBeInTheDocument();
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
    openDisplay();
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
    const traces = lastPlot().data as Array<{
      line: { color: string; width: number };
      opacity: number;
    }>;
    // The hovered sample keeps its colour and is drawn thicker; the reference dims.
    expect(traces[1].line).toEqual({ color: MEASURED_CURVE_COLORS.dark.selected, width: 3 });
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
    openDisplay();
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
    openDisplay();
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
    it("exports the run as Excel, CSV or PDF with the names it shows", () => {
      withAnalysis({ w2: { tm: 59, delta_tm: -1 } });
      if (melting.data) {
        melting.data.steps = [
          { changed_by: "u2" } as MeltingAnalysis["steps"][number],
          { changed_by: null, assigned_by: "u3" } as MeltingAnalysis["steps"][number],
          { changed_by: null, assigned_by: null } as MeltingAnalysis["steps"][number],
        ];
      }
      exported.length = 0;
      render(<RunCurvesPanel runId="r1" run={RUN} />);
      fireEvent.click(screen.getByRole("button", { name: "Export" }));
      expect(exported).toEqual([
        {
          formats: ["xlsx", "csv", "pdf"],
          request: {
            source: "run",
            format: "pdf",
            filename_hint: expect.stringMatching(/^run-.+-2026-11-13$/),
            payload: {
              run_id: "r1",
              people: { u1: "Ada Lovelace", u2: "grace@lab.org", u3: "Mary Anning" },
            },
          },
        },
      ]);
    });

    it("offers the peak actions on a completed run", () => {
      withAnalysis({ w2: { tm: 59, delta_tm: -1 } });
      (melting.data as MeltingAnalysis).steps = [
        {
          id: "s1",
          well_id: "w2",
          channel_key: "a",
          source: "instrument",
          value: 59,
          instrument_value: 59,
          instrument_label: null,
          status: "unreviewed",
          reason: null,
          changed_by: null,
          changed_at: null,
          assigned_window: null,
          assignment_reason: null,
          assigned_by: null,
          assigned_at: null,
          version: 1,
        },
      ];
      render(<RunCurvesPanel runId="r1" run={{ ...RUN, status: "completed" }} />);
      for (const name of ["Mark reviewed", "Add peak"])
        expect(screen.getByRole("button", { name })).toBeEnabled();
      fireEvent.keyDown(screen.getByRole("button", { name: "Actions for peak at 59 °C" }), {
        key: "Enter",
      });
      for (const name of ["Exclude peak", "Edit temperature"])
        expect(screen.getByRole("menuitem", { name })).toBeEnabled();
      // The only peak, inside the only transition: there is nothing to choose.
      expect(screen.queryByRole("menuitem", { name: "Use as Tm" })).not.toBeInTheDocument();
    });

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
      const toggle = screen.getByRole("switch", { name: "Reference traces" });
      expect(toggle).toBeChecked();
      expect(drawnWells()).toEqual(expect.arrayContaining(["w1", "w2"]));
      // It sits in the viewer's toolbar, not the results header.
      const results = screen.getByRole("heading", { name: "Results" }).closest("section");
      expect(results?.contains(toggle)).toBe(false);
    });

    it("lays the viewer out for review: short plot, selection line, steps, chart, then values", () => {
      withAnalysis({ w2: { tm: 59, delta_tm: -1 } });
      render(<RunCurvesPanel runId="r1" />);
      expect(lastPlot().style?.height).toBe(340);
      const line = screen.getByText("ABC-0000002 · Position 2 · 50 µM");
      const steps = screen.getByRole("heading", { name: "Peaks" });
      const values = screen.getByRole("button", { name: "Instrument values" });
      const follows = (a: Node, b: Node) =>
        !!(a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING);
      expect(follows(screen.getByTestId("plot"), line)).toBe(true);
      expect(follows(line, steps)).toBe(true);
      expect(follows(steps, values)).toBe(true);
      // A compact key stands in for the generic legend.
      const key = screen.getByTestId("curve-key");
      for (const t of ["Reference", "Reviewed peak", "Unreviewed peak", "Onset"])
        expect(within(key).getByText(t)).toBeInTheDocument();
      // The key's swatches are the traces' colours: violet reference, orange selection.
      const swatch = (text: string) => within(key).getByText(text).querySelector("i");
      const { reference, selected } = MEASURED_CURVE_COLORS.dark;
      expect(swatch("Reference")).toHaveStyle({ borderTopColor: reference });
      expect(swatch("Selected sample")).toHaveStyle({ borderTopColor: selected });
      expect(screen.queryByText("Other positions")).toBeNull();
      expect(screen.queryByText(/The trace under the pointer/)).toBeNull();
      fireEvent.click(gridRow("Position 3"), { metaKey: true });
      expect(screen.getByText("2 samples selected")).toBeInTheDocument();
      expect(swatch("Selected samples")).toHaveStyle({ borderTopColor: selected });
      // A selected reference stays violet, so alone it has no orange swatch to explain.
      fireEvent.click(gridRow("Position 1"));
      expect(within(screen.getByTestId("curve-key")).queryByText(/^Selected sample/)).toBeNull();
    });

    it("filtering keeps the selection", () => {
      withAnalysis({ w2: { tm: 55, delta_tm: -5 }, w3: { flags: ["no_step_in_window"] } });
      render(<RunCurvesPanel runId="r1" run={RULE_RUN} />);
      expect(selectedRows()).toEqual(["w3"]);
      fireEvent.click(screen.getByRole("button", { name: "down 1" }));
      expect(document.querySelector('tr[data-row-id="w3"]')).toBeNull();
      expect(drawnWells()).toContain("w3");
    });

    it("hints at the results when nothing is selected", () => {
      withAnalysis({ w2: { tm: 59, delta_tm: -1 } });
      render(<RunCurvesPanel runId="r1" />);
      expect(
        screen.queryByText("Select a sample in the results to see its trace and peaks."),
      ).not.toBeInTheDocument();
      fireEvent.click(gridRow("Position 2"), { metaKey: true });
      expect(selectedRows()).toEqual([]);
      // One message; no steps panel and no chart.
      expect(
        screen.getAllByText("Select a sample in the results to see its trace and peaks."),
      ).toHaveLength(1);
      expect(screen.queryByRole("heading", { name: "Peaks" })).toBeNull();
      expect(screen.queryByText(/positions above/)).toBeNull();
    });

    it("opens edit labeling from thermal analysis settings", () => {
      withAnalysis({});
      render(<RunCurvesPanel runId="r1" run={RUN} />);
      analysisSetting("Edit labeling");
      expect(screen.getByTestId("edit-labelling")).toBeInTheDocument();
      expect(saveStep).not.toHaveBeenCalled();
    });

    it("the no-window note opens the setting up of windows", () => {
      withAnalysis({}, 0);
      render(<RunCurvesPanel runId="r1" run={RUN} />);
      expect(screen.queryByTestId("name-peaks")).not.toBeInTheDocument();
      const note = screen.getByText(/^No transition named on this signal\./);
      fireEvent.click(within(note).getByRole("button", { name: "Name transitions" }));
      expect(screen.getByTestId("name-peaks")).toBeInTheDocument();
    });

    it("an editor sets up windows on any run status, with every trace of the signal", () => {
      withAnalysis({});
      const draft = render(<RunCurvesPanel runId="r1" run={RUN} />);
      analysisSetting("Name transitions");
      expect(naming.at(-1)).toMatchObject({
        open: true,
        runId: "r1",
        protocolId: "p1",
        analysis: melting.data,
        canRecalculate: true,
      });
      // Nothing is selected or drawn, yet the reference's trace is there to propose from.
      expect(naming.at(-1)?.set.curves.has("w1")).toBe(true);
      draft.unmount();
      // Naming changes the protocol, not the run: offered, but the run is not recalculated.
      for (const run of [
        { ...RUN, status: "approved" as const },
        { ...RUN, is_locked: true },
      ]) {
        const view = render(<RunCurvesPanel runId="r1" run={run} />);
        analysisSetting("Name transitions");
        expect(naming.at(-1)).toMatchObject({ open: true, canRecalculate: false });
        view.unmount();
      }
    });

    it("a viewer is not offered the setting up of windows", () => {
      canEdit.value = false;
      withAnalysis({}, 0);
      const none = render(<RunCurvesPanel runId="r1" run={RUN} />);
      expect(screen.getByText("No transition named on this signal.")).toBeInTheDocument();
      expect(screen.queryByRole("button", { name: /name transitions/i })).not.toBeInTheDocument();
      expect(naming).toHaveLength(0);
      none.unmount();
      // Nor the quiet Edit beside a window that is already there.
      withAnalysis({});
      render(<RunCurvesPanel runId="r1" run={RUN} />);
      expect(screen.queryByRole("button", { name: /name transitions/i })).not.toBeInTheDocument();
      expect(screen.queryByText("Edit")).not.toBeInTheDocument();
    });

    it("shows a placeholder while the results load", () => {
      melting.isLoading = true;
      render(<RunCurvesPanel runId="r1" />);
      expect(screen.getByTestId("results-loading")).toBeInTheDocument();
      expect(screen.queryByRole("button", { name: "Position 1" })).not.toBeInTheDocument();
    });
  });
});

describe("RunCurvesPanel concentration chart and window bands", () => {
  const dosed = {
    ...curves,
    positions: curves.positions.map((p, i) =>
      i === 1 || i === 2
        ? {
            ...p,
            registration_number: "REG-1",
            batch_id: "b1",
            batch_number: "REG-1-B2",
            dose: i === 1 ? 10 : 50,
          }
        : p,
    ),
  };
  const setup = () => {
    useRunCurves.mockImplementation(() => ({
      data: dosed,
      isLoading: false,
      isPlaceholderData: false,
    }));
    withAnalysis({ w2: { delta_tm: 2.5 }, w3: { delta_tm: 4 } });
    const main = melting.data?.windows[0] as NonNullable<typeof melting.data>["windows"][number];
    (melting.data as MeltingAnalysis).windows.push({ ...main, window: "Alt", low: 10, high: 30 });
    render(<RunCurvesPanel runId="r1" run={RUN} />);
  };
  const bands = () =>
    // The trace plot is the last one drawn that has bands (the chart's rect has no label).
    (
      plotCalls
        .map((c) => c.layout.shapes as { fillcolor?: string; label?: { text: string } }[])
        .filter((sh) => sh?.some((s) => s.label))
        .at(-1) ?? []
    )
      .filter((s) => s.label)
      .map((s) => [s.label?.text, s.fillcolor !== "rgba(0,0,0,0)"]);

  it("titles the chart by batch and lead window, and follows the window", () => {
    setup();
    fireEvent.click(gridRow("Position 2"));
    expect(screen.getByText("REG-1 · B2 — ΔTm (Main) by concentration")).toBeInTheDocument();
    choose("Analysis transition", "Alt 10–30 °C");
    expect(screen.getByText("REG-1 · B2 — ΔTm (Alt) by concentration")).toBeInTheDocument();
  });

  describe("concentrations without a ΔTm", () => {
    /** Batch b1 at 10, 50 and 100 µM (positions 2 to 4). */
    const three = {
      ...dosed,
      positions: dosed.positions.map((p, i) =>
        i === 3
          ? {
              ...p,
              registration_number: "REG-1",
              batch_id: "b1",
              batch_number: "REG-1-B2",
              dose: 100,
            }
          : p,
      ),
    };
    const show = (cells: Parameters<typeof withAnalysis>[0]) => {
      useRunCurves.mockImplementation(() => ({
        data: three,
        isLoading: false,
        isPlaceholderData: false,
      }));
      withAnalysis(cells);
      render(<RunCurvesPanel runId="r1" run={RUN} />);
      fireEvent.click(gridRow("Position 2"));
    };

    it("the chart's caption counts them", () => {
      show({ w2: { delta_tm: 2.5 }, w3: { delta_tm: 4 } });
      expect(screen.getByText("No ΔTm at 1 of 3 concentrations")).toBeInTheDocument();
    });

    it("joins the count to the batch's series values", () => {
      useRunCurves.mockImplementation(() => ({
        data: three,
        isLoading: false,
        isPlaceholderData: false,
      }));
      withAnalysis({ w2: { delta_tm: 2.5 }, w3: { delta_tm: 4 } });
      (melting.data as MeltingAnalysis).windows[0].series = [
        {
          readout_id: "rd-max",
          readout_name: "Max ΔTm (Main)",
          measure: "max_delta_tm",
          threshold: null,
          concentration: null,
          values: [{ batch_id: "b1", value: 4, qualifier: "=", concentration: 50 }],
        },
      ];
      render(<RunCurvesPanel runId="r1" run={RUN} />);
      fireEvent.click(gridRow("Position 2"));
      expect(
        screen.getByText("Max ΔTm +4.0 °C at 50 µM · No ΔTm at 1 of 3 concentrations"),
      ).toBeInTheDocument();
    });

    it("says so in place of the chart when fewer than two have one", () => {
      show({ w2: { delta_tm: 2.5 } });
      expect(
        screen.getByText("No ΔTm at 2 of 3 concentrations; nothing to chart"),
      ).toBeInTheDocument();
      expect(screen.queryByText(/by concentration/)).not.toBeInTheDocument();
    });

    it("says nothing when every concentration has a ΔTm", () => {
      show({ w2: { delta_tm: 2.5 }, w3: { delta_tm: 4 }, w4: { delta_tm: 5 } });
      expect(screen.getByText(/by concentration/)).toBeInTheDocument();
      expect(screen.queryByText(/No ΔTm at/)).not.toBeInTheDocument();
    });
  });

  it("shows the batch's stored series values under the chart title", () => {
    useRunCurves.mockImplementation(() => ({
      data: dosed,
      isLoading: false,
      isPlaceholderData: false,
    }));
    withAnalysis({ w2: { delta_tm: 2.5 }, w3: { delta_tm: 4 } });
    const main = (melting.data as MeltingAnalysis).windows[0];
    main.series = [
      {
        readout_id: "rd-max",
        readout_name: "Max ΔTm (Main)",
        measure: "max_delta_tm",
        threshold: null,
        concentration: null,
        values: [{ batch_id: "b1", value: 4, qualifier: "=", concentration: 50 }],
      },
    ];
    render(<RunCurvesPanel runId="r1" run={RUN} />);
    fireEvent.click(gridRow("Position 2"));
    expect(screen.getByText("Max ΔTm +4.0 °C at 50 µM")).toBeInTheDocument();
  });

  it("shows no chart for a sample without a batch", () => {
    setup();
    fireEvent.click(gridRow("Position 4"));
    expect(screen.queryByText(/by concentration/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Only one concentration/)).not.toBeInTheDocument();
  });

  it("says when the batch was tested at one concentration only", () => {
    useRunCurves.mockImplementation(() => ({
      data: {
        ...dosed,
        positions: dosed.positions.map((p, i) =>
          i === 3 ? { ...p, registration_number: "REG-2", batch_id: "b2", dose: 50 } : p,
        ),
      },
      isLoading: false,
      isPlaceholderData: false,
    }));
    withAnalysis({ w2: { delta_tm: 2.5 }, w3: { delta_tm: 4 }, w4: { delta_tm: 1 } });
    render(<RunCurvesPanel runId="r1" run={RUN} />);
    fireEvent.click(gridRow("REG-2"));
    expect(
      screen.getByText("Only one concentration of this batch in this run."),
    ).toBeInTheDocument();
    expect(screen.queryByText(/by concentration/)).not.toBeInTheDocument();
    fireEvent.click(gridRow("Position 2"));
    expect(screen.queryByText(/Only one concentration/)).not.toBeInTheDocument();
  });

  it("fills only the lead window's band, and all of them in Compare", () => {
    setup();
    expect(bands()).toEqual([
      ["Main", true],
      ["Alt", false],
    ]);
    choose("Analysis transition", "Alt 10–30 °C");
    expect(bands()).toEqual([
      ["Main", false],
      ["Alt", true],
    ]);
    choose("Analysis transition", "Compare transitions");
    expect(bands()).toEqual([
      ["Main", true],
      ["Alt", true],
    ]);
  });

  describe("hit rule", () => {
    it("the run's recorded rule calls the hits and counts them", () => {
      withAnalysis({
        w2: { tm: 55, delta_tm: -5 },
        w3: { tm: 63, delta_tm: 3 },
        w4: { tm: 61, delta_tm: 1 },
      });
      render(<RunCurvesPanel runId="r1" run={RULE_RUN} />);
      expect(screen.getByRole("button", { name: "Hit rule details" })).toHaveTextContent(
        "ΔTm (Main) outside -2 – 2",
      );
      expect(screen.getByRole("button", { name: "Hits 2" })).toBeInTheDocument();
      expect(screen.getByRole("button", { name: "up 1" })).toBeInTheDocument();
      expect(screen.getByRole("button", { name: "down 1" })).toBeInTheDocument();
    });

    it("an unset run shows the recommendation and calls no hits until applied", () => {
      withAnalysis({ w2: { tm: 55, delta_tm: -5 } });
      render(<RunCurvesPanel runId="r1" run={RUN} />);
      fireEvent.click(screen.getByRole("button", { name: "Hit rule details" }));
      expect(
        screen.getByText("Protocol recommends: ΔTm (Main) outside -2 – 2"),
      ).toBeInTheDocument();
      expect(screen.queryByRole("button", { name: /^Hits/ })).toBeNull();
      fireEvent.click(screen.getByRole("button", { name: "Apply to this run" }));
      expect(setHitCriteria).toHaveBeenCalledWith({ runId: "r1", criteria: [OUTSIDE] });
    });

    it("does not read or write a stored threshold", () => {
      const get = vi.spyOn(Storage.prototype, "getItem");
      withAnalysis({ w2: { tm: 55, delta_tm: -5 } });
      render(<RunCurvesPanel runId="r1" run={RULE_RUN} />);
      expect(get).not.toHaveBeenCalledWith("cellar.thermalShift.threshold");
      get.mockRestore();
    });
  });
});

describe("RunCurvesPanel picking on the plot", () => {
  // Traces from 20 to 90 °C, so a click reaches 1.4 °C while all of it is in view.
  const wide = { ...curves, curves: curves.curves.map((c) => ({ ...c, x: [20, 55, 90] })) };
  const peak = (id: string, value: number, status = "unreviewed") =>
    ({
      id,
      well_id: "w2",
      channel_key: "a",
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
      version: 1,
    }) as MeltingAnalysis["steps"][number];

  /** Position 2 selected, with peaks at 63.4 (accepted) and 48.1; the reference
   *  (Position 1) is drawn too and has no peaks. Windows Main and Low. */
  const setup = (over: Partial<MeltingAnalysis> = {}) => {
    useRunCurves.mockImplementation((_runId: string, params: { view?: string }) => ({
      data: params.view === "derivative" ? { ...wide, view: "derivative", window: 3.5 } : wide,
      isLoading: false,
      isPlaceholderData: false,
    }));
    withAnalysis({ w2: { tm: 63.4, delta_tm: 3.4 } });
    const a = melting.data as MeltingAnalysis;
    a.windows = [
      { ...a.windows[0], low: 50, high: 85 },
      { ...a.windows[0], window: "Low", low: 25, high: 50 },
    ];
    a.steps = [peak("p1", 63.4, "accepted"), peak("p2", 48.1)];
    Object.assign(a, over);
    render(<RunCurvesPanel runId="r1" run={RUN} />);
  };

  /** The props whose handlers the plot has: react-plotly attaches the event
   *  handlers of a render only when that render changes the figure. */
  const attached = () => {
    let at = plotCalls[0];
    let previous = at;
    for (const call of plotCalls) {
      if (call.data !== previous.data || call.layout !== previous.layout) at = call;
      previous = call;
    }
    return at;
  };
  const clickTrace = (wellId: string, x: number) =>
    act(() => attached().onClick?.({ points: [{ x, y: 1, data: { meta: wellId } }] }));
  const zoom = (event: Record<string, unknown>) => act(() => attached().onRelayout?.(event));
  const bar = (kind: "Peak" | "Spot") => screen.getByRole("region", { name: `${kind} picked` });
  const noBar = () => screen.queryByRole("region", { name: /picked$/ }) === null;
  const inBar = (kind: "Peak" | "Spot", name: string) =>
    fireEvent.click(within(bar(kind)).getByRole("button", { name }));
  /** The width of each peak line of Position 2, by temperature. */
  const peakWidths = () =>
    Object.fromEntries(
      (lastPlot().layout.shapes as { type: string; x0: number; line: { width: number } }[])
        .filter((sh) => sh.type === "line" && [48.1, 63.4].includes(sh.x0))
        .map((sh) => [sh.x0, sh.line.width]),
    );
  const pickedRows = () =>
    [...document.querySelectorAll("li[data-picked]")].map((li) => li.textContent);

  it("a click near a peak picks it: the bar, a wider line, the list row; nothing is saved", () => {
    setup();
    expect(noBar()).toBe(true);
    clickTrace("w2", 48.4);
    expect(bar("Peak")).toHaveTextContent("Position 2 · peak at 48.1 °C · From instrument");
    expect(peakWidths()).toEqual({ 48.1: 4, 63.4: 1.5 });
    expect(pickedRows()).toHaveLength(1);
    expect(pickedRows()[0]).toContain("48.1");
    // Picking another peak moves the pick.
    clickTrace("w2", 63);
    expect(bar("Peak")).toHaveTextContent("peak at 63.4 °C · From instrument · Reviewed");
    expect(peakWidths()).toEqual({ 48.1: 1.5, 63.4: 4 });
    expect(saveStep).not.toHaveBeenCalled();
  });

  it("a click away from every peak picks the spot", () => {
    setup();
    clickTrace("w2", 52.3046);
    expect(bar("Spot")).toHaveTextContent("Position 2 · 52.3 °C");
    expect(peakWidths()).toEqual({ 48.1: 1.5, 63.4: 1.5 });
    expect(pickedRows()).toEqual([]);
  });

  it("a click on a reference trace with no peaks picks a spot there, and can add a peak", () => {
    setup();
    clickTrace("w1", 52.3046);
    expect(bar("Spot")).toHaveTextContent("Position 1 · 52.3 °C");
    inBar("Spot", "Add and use as Tm (Low)");
    expect(screen.getByText("Add a peak")).toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: "Position" })).toHaveTextContent(
      "Position 1 · Protein alone",
    );
    expect(screen.getByLabelText("Value")).toHaveValue(52.3);
    expect(screen.getByRole("combobox", { name: "Transition" })).toHaveTextContent("Low 25–50 °C");
    expect(saveStep).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(saveStep).toHaveBeenCalledWith(
      { well_id: "w1", channel_key: "a", value: 52.3, assigned_window: "Low" },
      expect.anything(),
    );
  });

  it("a click on the reference's trace where the selected trace runs through it picks on the selected position", () => {
    setup();
    const click = (wellId: string, y: number) =>
      act(() => attached().onClick?.({ points: [{ x: 55, y, data: { meta: wellId } }] }));
    // Every trace runs through 2 at 55 °C; Position 2 is selected, the reference only drawn.
    click("w1", 2.05);
    expect(bar("Spot")).toHaveTextContent("Position 2 · 55 °C");
    // Away from the selected trace, the click is the reference's.
    click("w1", 2.5);
    expect(bar("Spot")).toHaveTextContent("Position 1 · 55 °C");
    // Zoomed in on y, the same distance is no longer the same spot.
    zoom({ "yaxis.range[0]": 1.9, "yaxis.range[1]": 2.1 });
    click("w1", 2.05);
    expect(bar("Spot")).toHaveTextContent("Position 1 · 55 °C");
    zoom({ "yaxis.autorange": true });
    click("w1", 2.05);
    expect(bar("Spot")).toHaveTextContent("Position 2 · 55 °C");
    // Another view draws its y axis anew: a zoom of the old one went with it.
    zoom({ "yaxis.range[0]": 1.9, "yaxis.range[1]": 2.1 });
    fireEvent.mouseDown(screen.getByRole("tab", { name: "Derivative" }));
    click("w1", 2.05);
    expect(bar("Spot")).toHaveTextContent("Position 2 · 55 °C");
  });

  describe("after a peak is added by hand", () => {
    /** The save answers with the new peak, and the analysis read after it has the peak. */
    const saved = (value: number) => {
      const added = { ...peak("p3", value), source: "manual" as const, instrument_value: null };
      const a = melting.data as MeltingAnalysis;
      melting.data = { ...a, steps: [...a.steps, added] };
      const callbacks = saveStep.mock.calls.at(-1)?.[1];
      act(() => callbacks.onSuccess({ step: added, recalculated: true, compute_warning: null }));
    };

    it("the spot it was added at becomes the picked peak, with nothing more to add there", () => {
      setup();
      clickTrace("w2", 52.3046);
      inBar("Spot", "Add a peak here");
      fireEvent.click(screen.getByRole("button", { name: "Save" }));
      saved(52.3);
      expect(bar("Peak")).toHaveTextContent("Position 2 · peak at 52.3 °C · Placed by hand");
      expect(screen.queryByRole("region", { name: "Spot picked" })).toBeNull();
      expect(screen.queryByRole("button", { name: "Add a peak here" })).toBeNull();
      expect(pickedRows()).toHaveLength(1);
      expect(pickedRows()[0]).toContain("52.3");
    });

    it("from the list's Add peak with nothing picked, nothing is picked", () => {
      setup();
      fireEvent.click(screen.getByRole("button", { name: "Add peak" }));
      fireEvent.change(screen.getByLabelText("Value"), { target: { value: "52.3" } });
      fireEvent.click(screen.getByRole("button", { name: "Save" }));
      saved(52.3);
      expect(noBar()).toBe(true);
      expect(pickedRows()).toEqual([]);
    });
  });

  it("picks in the derivative view too", () => {
    setup();
    fireEvent.mouseDown(screen.getByRole("tab", { name: "Derivative" }));
    clickTrace("w2", 48.4);
    expect(bar("Peak")).toHaveTextContent("peak at 48.1 °C");
  });

  it("Use as Tm (Main) opens that form with Main chosen", () => {
    setup();
    clickTrace("w2", 48.4);
    inBar("Peak", "Use as Tm (Main)");
    expect(screen.getByText("Use the peak at 48.1 °C on Position 2 as Tm")).toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: "Transition" })).toHaveTextContent("Main 50–85 °C");
    expect(saveStep).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(saveStep).toHaveBeenCalledWith(
      { stepId: "p2", body: { expected_version: 1, window: "Main" } },
      expect.anything(),
    );
  });

  it("Exclude opens that form; Mark reviewed saves at once, as in the list", () => {
    setup();
    clickTrace("w2", 48.4);
    inBar("Peak", "Exclude");
    expect(screen.getByText("Exclude the peak at 48.1 °C on Position 2")).toBeInTheDocument();
    expect(saveStep).not.toHaveBeenCalled();
    inBar("Peak", "Mark reviewed");
    expect(saveStep).toHaveBeenCalledWith(
      { stepId: "p2", body: { expected_version: 1, status: "accepted", value: 48.1 } },
      expect.anything(),
    );
  });

  it("Move, then a click on the same trace, opens Edit temperature with that temperature", () => {
    setup();
    clickTrace("w2", 48.4);
    inBar("Peak", "Move");
    expect(
      within(bar("Peak")).getByText("Click the new temperature on this position's trace."),
    ).toBeInTheDocument();
    clickTrace("w2", 52.3046);
    expect(
      screen.getByText("Edit the temperature of the peak at 48.1 °C on Position 2"),
    ).toBeInTheDocument();
    expect(screen.getByLabelText("Value")).toHaveValue(52.3);
    // The pick stays on the peak, and moving is over: the next click fills the form's value.
    expect(bar("Peak")).toHaveTextContent("peak at 48.1 °C");
    expect(within(bar("Peak")).queryByText(/Click the new temperature/)).toBeNull();
    clickTrace("w2", 52.6);
    expect(screen.getByLabelText("Value")).toHaveValue(52.6);
    expect(saveStep).not.toHaveBeenCalled();
  });

  it("while moving, a click on another position's trace picks there instead", () => {
    setup();
    clickTrace("w2", 48.4);
    inBar("Peak", "Move");
    clickTrace("w1", 52.3);
    expect(bar("Spot")).toHaveTextContent("Position 1 · 52.3 °C");
    expect(screen.queryByText(/^Edit the temperature of the peak/)).toBeNull();
    // Moving was given up: a click back on Position 2 only picks.
    clickTrace("w2", 60);
    expect(bar("Spot")).toHaveTextContent("Position 2 · 60 °C");
    expect(screen.queryByText(/^Edit the temperature of the peak/)).toBeNull();
  });

  it("Escape clears the pick", () => {
    setup();
    clickTrace("w2", 48.4);
    inBar("Peak", "Move");
    fireEvent.keyDown(document.body, { key: "Escape" });
    expect(noBar()).toBe(true);
    expect(peakWidths()).toEqual({ 48.1: 1.5, 63.4: 1.5 });
    expect(pickedRows()).toEqual([]);
    // Moving went with it.
    clickTrace("w2", 48.4);
    expect(within(bar("Peak")).queryByText(/Click the new temperature/)).toBeNull();
    expect(screen.queryByText(/^Edit the temperature of the peak/)).toBeNull();
  });

  it("the pick goes when its position is no longer drawn, or the signal changes", () => {
    setup();
    clickTrace("w1", 52.3);
    expect(bar("Spot")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("switch", { name: "Reference traces" }));
    expect(noBar()).toBe(true);
    clickTrace("w2", 52.3);
    expect(bar("Spot")).toBeInTheDocument();
    choose("Signal", "Signal B");
    expect(noBar()).toBe(true);
  });

  it("zooming in makes picking finer; resetting the zoom makes it coarse again", () => {
    setup();
    clickTrace("w2", 48.6);
    expect(bar("Peak")).toHaveTextContent("peak at 48.1 °C");
    zoom({ "xaxis.range[0]": 46, "xaxis.range[1]": 51 });
    clickTrace("w2", 48.6);
    expect(bar("Spot")).toHaveTextContent("Position 2 · 48.6 °C");
    // A zoom of the other axis leaves the reach as it is.
    zoom({ "yaxis.range[0]": 0, "yaxis.range[1]": 1 });
    clickTrace("w2", 48.6);
    expect(bar("Spot")).toBeInTheDocument();
    zoom({ "xaxis.autorange": true, "yaxis.autorange": true });
    clickTrace("w2", 48.6);
    expect(bar("Peak")).toHaveTextContent("peak at 48.1 °C");
  });

  it("on a run that cannot be edited, the bar shows the facts and why, and no buttons", () => {
    const refusal = "Peaks cannot be changed on an approved run";
    setup({ edit_refusal: refusal });
    clickTrace("w2", 48.4);
    expect(bar("Peak")).toHaveTextContent("Position 2 · peak at 48.1 °C · From instrument");
    expect(bar("Peak")).toHaveTextContent(refusal);
    expect(within(bar("Peak")).queryAllByRole("button")).toHaveLength(0);
    clickTrace("w1", 52.3);
    expect(bar("Spot")).toHaveTextContent(refusal);
    expect(within(bar("Spot")).queryAllByRole("button")).toHaveLength(0);
  });

  it("for a viewer, the bar shows the facts and that access is read-only, and no buttons", () => {
    canEdit.value = false;
    setup();
    clickTrace("w2", 48.4);
    expect(bar("Peak")).toHaveTextContent("peak at 48.1 °C");
    expect(bar("Peak")).toHaveTextContent("Read-only access — peaks cannot be changed.");
    expect(within(bar("Peak")).queryAllByRole("button")).toHaveLength(0);
  });
});

describe("thermal workspace", () => {
  function setupThermal(includeOtherControls = false) {
    const thermalPositions = positions.map((p, i) =>
      i === 8
        ? { ...p, well_type: "positive_control", label: "CoA", batch_id: "control-stock" }
        : includeOtherControls && i === 7
          ? { ...p, well_type: "negative_control", label: "Vehicle", batch_id: "control-stock" }
          : includeOtherControls && i === 6
            ? { ...p, well_type: "blank", label: "Buffer" }
            : p,
    );
    useRunCurves.mockReturnValue({
      data: { ...curves, positions: thermalPositions },
      isLoading: false,
      isPlaceholderData: false,
    });
    withAnalysis({
      w1: { tm: 60, delta_tm: 0, step_id: "p-w1", named_by: "range" },
      w2: { tm: 68, delta_tm: 8, step_id: "p-w2", named_by: "range" },
      w3: { tm: 65, delta_tm: 5, step_id: "p-w3", named_by: "range" },
      w9: { tm: 66, delta_tm: 6, step_id: "p-w9", named_by: "range" },
      ...(includeOtherControls
        ? {
            w8: { tm: 60.2, delta_tm: 0.2, step_id: "p-w8", named_by: "range" as const },
            w7: { flags: ["no_step_in_window"] },
          }
        : {}),
    });
    const analysis = melting.data as MeltingAnalysis;
    analysis.steps = ["w1", "w2", "w3", "w9"].map((well, i) => ({
      id: `p-${well}`,
      well_id: well,
      channel_key: "a",
      source: "instrument",
      value: [60, 68, 65, 66][i],
      instrument_value: [60, 68, 65, 66][i],
      instrument_label: null,
      status: i === 0 ? "accepted" : "unreviewed",
      reason: null,
      changed_by: null,
      changed_at: null,
      assigned_window: null,
      assignment_reason: null,
      assigned_by: null,
      assigned_at: null,
      version: 3,
    }));
    if (includeOtherControls)
      analysis.steps.push({
        ...analysis.steps[3],
        id: "p-w8",
        well_id: "w8",
        value: 60.2,
        instrument_value: 60.2,
        status: "accepted",
      });
    return render(<RunCurvesPanel runId="r1" run={RUN} />);
  }

  it("keeps controls available outside the compound table and links them to their traces", () => {
    setupThermal();
    const summary = screen.getByRole("region", { name: "Thermal analysis summary" });
    expect(within(summary).getByText("Positive Control")).toBeInTheDocument();
    expect(
      within(summary).getByRole("button", {
        name: "View CoA positive control trace at Position 9",
      }),
    ).toBeInTheDocument();
    expect(summary).toHaveTextContent("ΔTm +6.0 °C");
    expect(document.querySelector('tr[data-row-id="w1"]')).toBeNull();
    expect(document.querySelector('tr[data-row-id="w9"]')).toBeNull();
    expect(screen.queryByRole("columnheader", { name: "Hit" })).toBeNull();
    expect(within(summary).getByRole("button", { name: "2 unreviewed compounds" })).toBeEnabled();
    fireEvent.click(within(summary).getByRole("button", { name: /CoA/ }));
    expect(screen.getByRole("heading", { name: "CoA" })).toBeInTheDocument();
    expect(drawnWells()).toContain("w9");
    fireEvent.click(within(summary).getByRole("button", { name: /Protein alone/ }));
    expect(screen.getByRole("heading", { name: "Protein alone" })).toBeInTheDocument();
    expect(saveStep).not.toHaveBeenCalled();
  });

  it("overlays a positive control without replacing the compound and keeps it while browsing", () => {
    setupThermal();
    const overlay = screen.getByRole("button", { name: "Overlay CoA positive control" });
    expect(overlay).toHaveAttribute("aria-pressed", "false");
    fireEvent.click(overlay);
    expect(overlay).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByLabelText("Selected sample")).toHaveTextContent("ABC-0000002");
    expect(selectedRows()).toEqual(["w2"]);
    expect(drawnWells()).toEqual(expect.arrayContaining(["w1", "w2", "w9"]));
    const sampleLine = lastPlot().data.find((t) => t.meta === "w2")?.line;
    const controlLine = lastPlot().data.find((t) => t.meta === "w9")?.line;
    expect(controlLine).not.toEqual(sampleLine);
    expect(screen.getByTestId("curve-key")).toHaveTextContent(
      "CoA · Positive Control · Position 9",
    );
    fireEvent.click(gridRow("Position 3"));
    expect(screen.getByLabelText("Selected sample")).toHaveTextContent("ABC-0000003");
    expect(drawnWells()).toEqual(expect.arrayContaining(["w1", "w3", "w9"]));
    fireEvent.click(overlay);
    expect(drawnWells()).not.toContain("w9");
    expect(drawnWells()).toContain("w3");
    expect(saveStep).not.toHaveBeenCalled();
  });

  it("keeps the positive control overlaid during review navigation and accepts only the selected sample", () => {
    setupThermal();
    fireEvent.click(screen.getByRole("button", { name: "Overlay CoA positive control" }));
    fireEvent.click(screen.getByRole("button", { name: "Next unreviewed" }));
    expect(screen.getByLabelText("Selected sample")).toHaveTextContent("ABC-0000003");
    expect(drawnWells()).toEqual(expect.arrayContaining(["w3", "w9"]));
    fireEvent.click(screen.getByRole("button", { name: "Mark reviewed" }));
    expect(saveStep).toHaveBeenCalledTimes(1);
    expect(saveStep).toHaveBeenCalledWith(
      { stepId: "p-w3", body: { expected_version: 3, status: "accepted", value: 65 } },
      expect.anything(),
    );
  });

  it("shows positive, negative and blank controls and overlays them independently", () => {
    setupThermal(true);
    const summary = screen.getByRole("region", { name: "Thermal analysis summary" });
    for (const name of ["Positive Control", "Negative Control", "Blank"])
      expect(within(summary).getByText(name)).toBeInTheDocument();
    expect(
      within(summary).getByRole("button", {
        name: "View Vehicle negative control trace at Position 8",
      }),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Overlay CoA positive control" }));
    fireEvent.click(screen.getByRole("button", { name: "Overlay Vehicle negative control" }));
    fireEvent.click(screen.getByRole("button", { name: "Overlay Buffer blank" }));
    expect(drawnWells()).toEqual(expect.arrayContaining(["w1", "w2", "w7", "w8", "w9"]));
    const color = (id: string) =>
      (lastPlot().data.find((t) => t.meta === id)?.line as { color: string }).color;
    expect(new Set([color("w1"), color("w2"), color("w8"), color("w9")]).size).toBe(4);
    expect(screen.getByTestId("curve-key")).toHaveTextContent(
      "Vehicle · Negative Control · Position 8",
    );
    expect(screen.getByTestId("curve-key")).toHaveTextContent("Buffer · Blank · Position 7");
    fireEvent.click(gridRow("Position 3"));
    expect(drawnWells()).toEqual(expect.arrayContaining(["w3", "w7", "w8", "w9"]));
    fireEvent.click(screen.getByRole("button", { name: "Overlay Vehicle negative control" }));
    expect(drawnWells()).not.toContain("w8");
    expect(drawnWells()).toContain("w9");
    expect(saveStep).not.toHaveBeenCalled();
  });

  it("filters unreviewed compounds while preserving the selected evidence", () => {
    setupThermal();
    fireEvent.click(gridRow("Position 4"));
    fireEvent.click(screen.getByRole("button", { name: "Unreviewed 2" }));
    expect(document.querySelector('tr[data-row-id="w4"]')).toBeNull();
    expect(selectedRows()).toEqual([]);
    expect(screen.getByRole("heading", { name: "ABC-0000004" })).toBeInTheDocument();
    expect(drawnWells()).toContain("w4");
    expect(document.querySelectorAll("tr[data-row-id]")).toHaveLength(2);
    expect(saveStep).not.toHaveBeenCalled();
  });

  it("keeps an identity above the plot when the last focused row is deselected", () => {
    setupThermal();
    fireEvent.click(gridRow("Position 3"), { metaKey: true });
    expect(screen.getByLabelText("Selected sample")).toHaveTextContent("ABC-0000003");
    fireEvent.click(gridRow("Position 3"), { metaKey: true });
    expect(screen.getByLabelText("Selected sample")).toHaveTextContent("ABC-0000002");
    expect(selectedRows()).toEqual(["w2"]);
  });

  it("moves through unreviewed peaks without saving, then accepts only the chosen peak", () => {
    setupThermal();
    expect(screen.getByRole("heading", { name: "ABC-0000002" })).toBeInTheDocument();
    const selected = screen.getByLabelText("Selected sample");
    expect(
      selected.compareDocumentPosition(screen.getByTestId("plot")) &
        Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Next unreviewed" }));
    expect(screen.getByRole("heading", { name: "ABC-0000003" })).toBeInTheDocument();
    expect(saveStep).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Mark reviewed" }));
    expect(saveStep).toHaveBeenCalledWith(
      { stepId: "p-w3", body: { expected_version: 3, status: "accepted", value: 65 } },
      expect.anything(),
    );
  });

  it("keeps the existing measured-trace layout for a nonthermal assay", () => {
    protocolData.value = { id: "p1", readout_definitions: [], recommended_hit_criteria: null };
    withAnalysis({}, 0);
    useRunCurves.mockReturnValue({
      data: { ...curves, channels: curves.channels.map((c) => ({ ...c, x_unit: "s" })) },
      isLoading: false,
      isPlaceholderData: false,
    });
    render(<RunCurvesPanel runId="r1" run={RUN} />);
    expect(screen.queryByRole("region", { name: "Thermal traces workspace" })).toBeNull();
    expect(screen.getByRole("tab", { name: "Signal A" })).toBeInTheDocument();
    expect(document.querySelector('tr[data-row-id="w1"]')).toBeInTheDocument();
  });

  it("keeps thermal review navigation available to viewers without offering edits", () => {
    canEdit.value = false;
    setupThermal();
    expect(screen.getByRole("button", { name: "Next unreviewed" })).toBeEnabled();
    expect(screen.queryByRole("button", { name: "Mark reviewed" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Review actions" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Analysis settings" })).toBeNull();
    expect(saveStep).not.toHaveBeenCalled();
  });
});
