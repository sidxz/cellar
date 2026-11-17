import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { MeltingAnalysis, MeltingStep, RunCurves } from "../types";

const plotProps: { onClick?: (ev: unknown) => void }[] = [];
vi.mock("@/shared/lib/plotly", () => ({
  Plot: (props: { onClick?: (ev: unknown) => void }) => {
    plotProps.push(props);
    return <div data-testid="plot" />;
  },
  getPlotlyGlobal: () => undefined,
}));

const useRunCurves = vi.fn();
vi.mock("../hooks/use-run-curves", () => ({
  useRunCurves: (...args: unknown[]) => useRunCurves(...args),
}));
const canEdit = { value: true };
vi.mock("@/shared/hooks/use-current-user", () => ({ useCanEdit: () => canEdit.value }));
vi.mock("./edit-labelling-dialog", () => ({ EditLabellingDialog: () => null }));
vi.mock("@/shared/components/data-grid/data-grid", async () => ({
  DataGrid: (await import("../test/test-data-grid")).TableGrid,
}));

const api = vi.fn();
/** The reads of a position's found peaks, apart from `api`, which tests replace whole. */
const found = vi.fn();
vi.mock("@/shared/lib/api/custom-instance", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/shared/lib/api/custom-instance")>()),
  customInstance: (req: { url: string }) =>
    req.url.endsWith("/peak-candidates") ? found(req) : api(req),
}));

import { ApiError } from "@/shared/lib/api/custom-instance";
import { gridRow } from "../test/test-data-grid";
import { RunCurvesPanel } from "./run-curves-panel";

function position(id: string, column: number, wellType: string, label: string, batch: string) {
  return {
    well_id: id,
    position: `A${column}`,
    row: "A",
    column,
    well_type: wellType,
    registration_number: null,
    batch_id: null,
    batch_number: batch,
    position_label: `Position ${column}`,
    label,
    note: null,
    dose: null,
  };
}

const positions = [
  position("w1", 1, "reference", "Protein alone", "B-001"),
  position("w2", 2, "sample", "ABC-0000002", "B-002"),
  position("w3", 3, "sample", "ABC-0000003", "B-003"),
];

const curves: RunCurves = {
  run_id: "r1",
  dose_unit: "uM",
  holder: { kind: "cassette", rows: 1, columns: 3, label: "Holder of 3" },
  positions,
  channels: [
    { key: "a", label: "Signal A", x_unit: "°C", y_unit: null, x_label: null },
    { key: "b", label: "Signal B", x_unit: "°C", y_unit: null, x_label: null },
  ],
  channel: "a",
  curves: positions.map((p) => ({
    well_id: p.well_id,
    x: [20, 50, 90],
    y: [1, 2, 3],
    reported: [],
  })),
  view: "measured",
  window: null,
};

function step(over: Partial<MeltingStep> & Pick<MeltingStep, "id" | "well_id">): MeltingStep {
  return {
    channel_key: "a",
    source: "instrument",
    value: 50,
    instrument_value: 50,
    instrument_label: "Tm1",
    status: "unreviewed",
    reason: null,
    changed_by: null,
    changed_at: null,
    assigned_window: null,
    assignment_reason: null,
    assigned_by: null,
    assigned_at: null,
    version: 1,
    ...over,
  };
}

const steps: MeltingStep[] = [
  step({ id: "s1", well_id: "w1", value: 36.6, instrument_value: 36.6 }),
  step({
    id: "s2",
    well_id: "w2",
    value: 64,
    instrument_value: 63.5,
    status: "accepted",
    reason: "shoulder peak",
    changed_by: "u1",
    changed_at: "2026-11-13T10:00:00Z",
    version: 2,
  }),
  step({
    id: "s3",
    well_id: "w2",
    source: "manual",
    value: 70.1,
    instrument_value: null,
    instrument_label: null,
    status: "rejected",
    reason: "noise",
    version: 3,
  }),
  step({ id: "s4", well_id: "w2", channel_key: "b", value: 55.5, instrument_value: 55.5 }),
  step({ id: "s5", well_id: "w3", value: 61.2, instrument_value: 61.2 }),
];

let analysis: MeltingAnalysis;

function win(window: string, low: number, high: number, channel = "a") {
  return {
    window,
    channel_key: channel,
    low,
    high,
    tm_readout_id: null,
    delta_tm_readout_id: null,
    reference_tm: null,
    reference_count: 0,
    flags: [],
    positions: [],
    series: [],
  };
}
/** Two windows on the shown signal and one on the other. */
const WINDOWS = [win("Low", 25, 50), win("Main", 50, 85), win("Wide", 20, 95, "b")];
/** Position 2 with a peak assigned to Main and one below it. */
const ASSIGNED = [
  step({
    id: "p1",
    well_id: "w2",
    value: 63.4,
    instrument_value: 63.4,
    status: "accepted",
    assigned_window: "Main",
    assignment_reason: "main transition",
    assigned_by: "u1",
    assigned_at: "2026-11-13T10:00:00Z",
    version: 4,
  }),
  step({ id: "p2", well_id: "w2", value: 48.1, instrument_value: 48.1 }),
];

/** Opens a Radix select by keyboard and picks an option. */
function choose(name: string, option: string) {
  fireEvent.keyDown(screen.getByRole("combobox", { name }), { key: "Enter" });
  fireEvent.click(screen.getByRole("option", { name: option }));
}

function change(s: MeltingStep, warning: string | null = null) {
  return { step: s, recalculated: true, compute_warning: warning };
}

beforeEach(() => {
  // Radix Select scrolls its listbox into view; jsdom has no such method.
  Element.prototype.scrollIntoView = vi.fn();
  plotProps.length = 0;
  analysis = {
    run_id: "r1",
    edit_refusal: null,
    steps,
    windows: [],
    step_checks: [],
    outside_every_window: [],
  };
  canEdit.value = true;
  useRunCurves.mockReset();
  useRunCurves.mockReturnValue({ data: curves, isLoading: false, isPlaceholderData: false });
  found.mockReset();
  found.mockResolvedValue({ signals: [] });
  api.mockReset();
  api.mockImplementation((req: { url: string; method: string }) => {
    if (req.url.endsWith("/melting-analysis")) return Promise.resolve(analysis);
    if (req.url.endsWith("/workspace-members"))
      return Promise.resolve([{ user_id: "u1", name: "Ada Lovelace", email: "ada@example.org" }]);
    return Promise.resolve(change(steps[0]));
  });
});

let qc: QueryClient;
function renderPanel() {
  qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  render(
    <QueryClientProvider client={qc}>
      <RunCurvesPanel runId="r1" />
    </QueryClientProvider>,
  );
}

/** Selects through the results grid, the position picker. */
async function select(...names: string[]) {
  await screen.findByRole("heading", { name: "Results" });
  for (const [i, name] of names.entries()) {
    fireEvent.click(gridRow(name), { metaKey: i > 0 });
  }
  return screen.findByRole("list", { name: "Peaks" });
}

function row(table: HTMLElement, text: string) {
  const r = within(table)
    .getAllByRole("listitem")
    .find((tr) => tr.textContent?.includes(text));
  if (!r) throw new Error(`no row with ${text}`);
  return r;
}

function writes() {
  return api.mock.calls
    .map(([req]) => req as { url: string; method: string; data?: unknown })
    .filter((r) => r.method !== "GET");
}

describe("MeltingStepsPanel", () => {
  it("lists steps of the selected positions with instrument value only when corrected", async () => {
    renderPanel();
    const table = await select("Position 1", "Position 2");
    // s1, s2, s3; s4 is on another signal and s5's position is not selected.
    expect(within(table).getAllByRole("listitem")).toHaveLength(3);
    expect(within(table).queryByText("55.5")).not.toBeInTheDocument();
    expect(within(table).queryByText("61.2")).not.toBeInTheDocument();

    const s1 = row(table, "36.6");
    expect(within(s1).getAllByText("36.6")).toHaveLength(1);
    expect(within(s1).getByText("Position 1")).toBeInTheDocument();
    expect(within(s1).getByText("From instrument")).toBeInTheDocument();
    expect(within(s1).queryByText("B-001")).not.toBeInTheDocument();
    expect(within(s1).queryByText(/was/)).not.toBeInTheDocument();

    const s2 = row(table, "64");
    expect(within(s2).getByText("was 63.5")).toBeInTheDocument();
    expect(within(s2).getByText("shoulder peak")).toBeInTheDocument();
    expect(await within(s2).findByText(/Ada Lovelace/)).toBeInTheDocument();

    const s3 = row(table, "70.1");
    expect(s3.className).toContain("line-through");
    expect(within(s3).getByText("Placed by hand · Excluded")).toBeInTheDocument();
  });

  it("names the position only when several are selected", async () => {
    renderPanel();
    const table = await select("Position 1");
    expect(within(table).queryByText("Position 1")).not.toBeInTheDocument();
    expect(within(table).getByText("36.6")).toBeInTheDocument();
  });

  it("requires a reason to reject and sends expected_version", async () => {
    api.mockImplementation((req: { url: string; method: string }) => {
      if (req.url.endsWith("/melting-analysis")) return Promise.resolve(analysis);
      if (req.url.endsWith("/workspace-members")) return Promise.resolve([]);
      return Promise.resolve(
        change({ ...steps[0], status: "rejected" }, "Recompute the run to update its results."),
      );
    });
    renderPanel();
    const table = await select("Position 1");
    fireEvent.click(within(row(table, "36.6")).getByRole("button", { name: "Exclude" }));
    const save = screen.getByRole("button", { name: "Save" });
    expect(save).toBeDisabled();
    fireEvent.change(screen.getByLabelText("Reason"), { target: { value: "bubble" } });
    fireEvent.click(save);
    await waitFor(() => expect(writes()).toHaveLength(1));
    expect(writes()[0]).toEqual({
      url: "/api/v1/melting-steps/s1",
      method: "PATCH",
      data: { expected_version: 1, status: "rejected", value: 36.6, reason: "bubble" },
    });
    expect(await screen.findByText("Recompute the run to update its results.")).toBeInTheDocument();
  });

  it("Use instrument value needs no reason", async () => {
    renderPanel();
    const table = await select("Position 2");
    fireEvent.click(within(row(table, "64")).getByRole("button", { name: "Edit temperature" }));
    expect(screen.getByLabelText("Value")).toHaveValue(64);
    expect(screen.getByLabelText("Reason")).toHaveValue("shoulder peak");
    fireEvent.click(screen.getByRole("button", { name: "Use instrument value" }));
    expect(screen.getByLabelText("Value")).toHaveValue(63.5);
    expect(screen.getByLabelText("Reason")).toHaveValue("");
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(writes()).toHaveLength(1));
    expect(writes()[0]).toEqual({
      url: "/api/v1/melting-steps/s2",
      method: "PATCH",
      data: { expected_version: 2, status: "accepted", value: 63.5 },
    });
  });

  it("shows the value to two decimals; saving it untouched sends the exact value, no reason", async () => {
    analysis = {
      ...analysis,
      steps: [step({ id: "s9", well_id: "w1", value: 36.606635, instrument_value: 36.606635 })],
    };
    renderPanel();
    const table = await select("Position 1");
    fireEvent.click(within(row(table, "36.61")).getByRole("button", { name: "Edit temperature" }));
    expect(screen.getByLabelText("Value")).toHaveValue(36.61);
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(writes()).toHaveLength(1));
    expect(writes()[0].data).toEqual({ expected_version: 1, status: "accepted", value: 36.606635 });
  });

  it("a plot click fills two decimals", async () => {
    renderPanel();
    await select("Position 3");
    fireEvent.click(screen.getByRole("button", { name: "Add peak" }));
    plotProps.at(-1)?.onClick?.({ points: [{ x: 32.646001, y: 2, data: { meta: "w3" } }] });
    await waitFor(() => expect(screen.getByLabelText("Value")).toHaveValue(32.65));
  });

  it("names the line switch Markers, since it covers steps and onsets", async () => {
    renderPanel();
    await select("Position 1");
    fireEvent.click(screen.getByRole("button", { name: "Display" }));
    expect(screen.getByRole("tablist", { name: "Markers" })).toBeInTheDocument();
  });

  it("cuts a long reason short and keeps the whole text on hover", async () => {
    const long = "shoulder at the start of the ramp, not an unfolding step";
    analysis = { ...analysis, steps: [{ ...steps[1], reason: long }] };
    renderPanel();
    const table = await select("Position 2");
    const cell = within(row(table, "64")).getByText(long);
    expect(cell).toHaveAttribute("title", long);
    expect(cell.className).toContain("truncate");
  });

  it("re-sends the current value and reason on Mark reviewed", async () => {
    analysis = { ...analysis, steps: [{ ...steps[1], status: "unreviewed" }] };
    renderPanel();
    const table = await select("Position 2");
    fireEvent.click(within(row(table, "64")).getByRole("button", { name: "Mark reviewed" }));
    await waitFor(() => expect(writes()).toHaveLength(1));
    expect(writes()[0].data).toEqual({
      expected_version: 2,
      status: "accepted",
      value: 64,
      reason: "shoulder peak",
    });
  });

  it("Mark reviewed on an excluded step pre-fills the exclusion reason and lets it be cleared", async () => {
    renderPanel();
    const table = await select("Position 2");
    fireEvent.click(within(row(table, "70.1")).getByRole("button", { name: "Mark reviewed" }));
    expect(writes()).toHaveLength(0);
    expect(screen.getByText("Mark the peak at 70.1 °C on Position 2 reviewed")).toBeInTheDocument();
    expect(
      screen.getByText(/^The reason below was given when the peak was excluded\./),
    ).toBeInTheDocument();
    expect(screen.getByLabelText("Reason")).toHaveValue("noise");
    fireEvent.change(screen.getByLabelText("Reason"), { target: { value: "" } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(writes()).toHaveLength(1));
    expect(writes()[0]).toEqual({
      url: "/api/v1/melting-steps/s3",
      method: "PATCH",
      data: { expected_version: 3, status: "accepted", value: 70.1 },
    });
  });

  it("Unmark sets a reviewed step back, keeping its value and reason", async () => {
    renderPanel();
    const table = await select("Position 2");
    fireEvent.click(within(row(table, "64")).getByRole("button", { name: "Unmark" }));
    await waitFor(() => expect(writes()).toHaveLength(1));
    expect(writes()[0].data).toEqual({
      expected_version: 2,
      status: "unreviewed",
      value: 64,
      reason: "shoulder peak",
    });
  });

  it("an unreviewed step offers no Unmark", async () => {
    renderPanel();
    const table = await select("Position 1");
    expect(
      within(row(table, "36.6")).queryByRole("button", { name: "Unmark" }),
    ).not.toBeInTheDocument();
  });

  it("a plot click fills the open form's value without saving", async () => {
    renderPanel();
    await select("Position 3");
    fireEvent.click(screen.getByRole("button", { name: "Add peak" }));
    const onClick = plotProps.at(-1)?.onClick;
    expect(onClick).toBeDefined();
    onClick?.({ points: [{ x: 52.3, y: 2, data: { meta: "w3" } }] });
    await waitFor(() => expect(screen.getByLabelText("Value")).toHaveValue(52.3));
    expect(writes()).toHaveLength(0);
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(writes()).toHaveLength(1));
    expect(writes()[0]).toEqual({
      url: "/api/v1/runs/r1/melting-steps",
      method: "POST",
      data: { well_id: "w3", channel_key: "a", value: 52.3 },
    });
  });

  it("shows the conflict message and Reload", async () => {
    const message = "This peak was changed by someone else. Reload and try again.";
    api.mockImplementation((req: { url: string; method: string }) => {
      if (req.url.endsWith("/melting-analysis")) return Promise.resolve(analysis);
      return Promise.reject(new ApiError(`API error: 409 — ${message}`, 409, { detail: message }));
    });
    renderPanel();
    const table = await select("Position 1");
    fireEvent.click(within(row(table, "36.6")).getByRole("button", { name: "Mark reviewed" }));
    expect(await screen.findByText(message)).toBeInTheDocument();
    const reads = () => api.mock.calls.filter(([r]) => r.url.endsWith("/melting-analysis")).length;
    const before = reads();
    fireEvent.click(screen.getByRole("button", { name: "Reload" }));
    await waitFor(() => expect(reads()).toBe(before + 1));
    await waitFor(() => expect(screen.queryByText(message)).not.toBeInTheDocument());
  });

  it("hides actions and shows the refusal on an approved run", async () => {
    const refusal = "Peaks cannot be changed on an approved run";
    analysis = {
      ...analysis,
      edit_refusal: refusal,
      steps: [{ ...steps[0], assigned_window: "Gone" }],
    };
    renderPanel();
    const table = await select("Position 1");
    expect(screen.getByText(refusal)).toBeInTheDocument();
    for (const name of [
      "Mark reviewed",
      "Exclude",
      "Edit temperature",
      "Unmark",
      "Add peak",
      "Use as Tm",
      "Clear",
    ]) {
      expect(screen.queryByRole("button", { name })).not.toBeInTheDocument();
    }
    expect(within(table).getByText("36.6")).toBeInTheDocument();
    expect(within(table).getByText(/^Set as Tm of 'Gone'/)).toBeInTheDocument();
  });

  describe("assigning", () => {
    beforeEach(() => {
      analysis = { ...analysis, windows: WINDOWS };
    });

    it("assigns a peak to a window of the shown signal, with no reason needed", async () => {
      renderPanel();
      const table = await select("Position 2");
      fireEvent.click(within(row(table, "64")).getByRole("button", { name: "Use as Tm" }));
      expect(screen.getByText("Use the peak at 64 °C on Position 2 as Tm")).toBeInTheDocument();
      // It starts on the transition whose range holds the peak.
      expect(screen.getByRole("combobox", { name: "Transition" })).toHaveTextContent(
        "Main 50–85 °C",
      );
      expect(screen.getByLabelText("Reason")).toHaveAttribute("placeholder", "Optional");
      fireEvent.keyDown(screen.getByRole("combobox", { name: "Transition" }), { key: "Enter" });
      // No transition was set by hand, so there is none to give back to the temperature range.
      expect(screen.getAllByRole("option").map((o) => o.textContent)).toEqual([
        "Low 25–50 °C",
        "Main 50–85 °C",
      ]);
      fireEvent.click(screen.getByRole("option", { name: "Low 25–50 °C" }));
      fireEvent.click(screen.getByRole("button", { name: "Save" }));
      await waitFor(() => expect(writes()).toHaveLength(1));
      expect(writes()[0]).toEqual({
        url: "/api/v1/melting-steps/s2/assignment",
        method: "PUT",
        data: { expected_version: 2, window: "Low" },
      });
    });

    it("offers Use as Tm on an excluded peak and sends the reason when one is given", async () => {
      renderPanel();
      const table = await select("Position 2");
      fireEvent.click(within(row(table, "70.1")).getByRole("button", { name: "Use as Tm" }));
      expect(screen.getByRole("combobox", { name: "Transition" })).toHaveTextContent(
        "Main 50–85 °C",
      );
      // The exclusion reason is the peak's, not the choice's.
      expect(screen.getByLabelText("Reason")).toHaveValue("");
      fireEvent.change(screen.getByLabelText("Reason"), { target: { value: " late transition " } });
      fireEvent.click(screen.getByRole("button", { name: "Save" }));
      await waitFor(() => expect(writes()).toHaveLength(1));
      expect(writes()[0]).toEqual({
        url: "/api/v1/melting-steps/s3/assignment",
        method: "PUT",
        data: { expected_version: 3, window: "Main", reason: "late transition" },
      });
    });

    it("shows an assigned peak's window, and says which peak a save replaces", async () => {
      analysis = { ...analysis, steps: ASSIGNED };
      renderPanel();
      const table = await select("Position 2");
      expect(within(row(table, "63.4")).getByText("Used as Tm (Main)")).toBeInTheDocument();
      expect(within(row(table, "48.1")).queryByText(/Used as Tm/)).not.toBeInTheDocument();

      const replaces =
        "Main is currently the peak at 63.4 °C on this position; saving replaces it.";
      fireEvent.click(within(row(table, "48.1")).getByRole("button", { name: "Use as Tm" }));
      // It starts on Low, whose range holds it.
      expect(screen.queryByText(replaces)).not.toBeInTheDocument();
      choose("Transition", "Main 50–85 °C");
      expect(screen.getByText(replaces)).toBeInTheDocument();
      choose("Transition", "Low 25–50 °C");
      expect(screen.queryByText(replaces)).not.toBeInTheDocument();

      // The peak set by hand opens on its own transition and reason; nothing is replaced.
      fireEvent.click(within(row(table, "63.4")).getByRole("button", { name: "Use as Tm" }));
      expect(screen.getByRole("combobox", { name: "Transition" })).toHaveTextContent(
        "Main 50–85 °C",
      );
      expect(screen.getByLabelText("Reason")).toHaveValue("main transition");
      expect(screen.queryByText(replaces)).not.toBeInTheDocument();
    });

    it("a spot picked on the plot adds a peak and names it in the same save", async () => {
      renderPanel();
      await select("Position 3");
      act(() => plotProps.at(-1)?.onClick?.({ points: [{ x: 52.3, y: 2, data: { meta: "w3" } }] }));
      const spot = screen.getByRole("region", { name: "Spot picked" });
      fireEvent.click(within(spot).getByRole("button", { name: "Add and use as Tm (Main)" }));
      expect(screen.getByLabelText("Value")).toHaveValue(52.3);
      expect(screen.getByRole("combobox", { name: "Transition" })).toHaveTextContent(
        "Main 50–85 °C",
      );
      expect(writes()).toHaveLength(0);
      choose("Transition", "Low 25–50 °C");
      fireEvent.click(screen.getByRole("button", { name: "Save" }));
      await waitFor(() => expect(writes()).toHaveLength(1));
      expect(writes()[0]).toEqual({
        url: "/api/v1/runs/r1/melting-steps",
        method: "POST",
        data: { well_id: "w3", channel_key: "a", value: 52.3, assigned_window: "Low" },
      });
    });

    it("a peak added at a picked spot is the picked peak before the analysis is read again", async () => {
      const added = step({
        id: "s9",
        well_id: "w3",
        source: "manual",
        value: 52.3,
        instrument_value: null,
        instrument_label: null,
      });
      let saved = false;
      api.mockImplementation((req: { url: string; method: string }) => {
        if (req.method === "POST") {
          saved = true;
          return Promise.resolve(change(added));
        }
        // The read that follows the save does not come back.
        if (req.url.endsWith("/melting-analysis"))
          return saved ? new Promise(() => {}) : Promise.resolve(analysis);
        return Promise.resolve([]);
      });
      renderPanel();
      await select("Position 3");
      act(() => plotProps.at(-1)?.onClick?.({ points: [{ x: 52.3, y: 2, data: { meta: "w3" } }] }));
      fireEvent.click(
        within(screen.getByRole("region", { name: "Spot picked" })).getByRole("button", {
          name: "Add a peak here",
        }),
      );
      fireEvent.click(screen.getByRole("button", { name: "Save" }));
      expect(await screen.findByRole("region", { name: "Peak picked" })).toHaveTextContent(
        "Position 3 · peak at 52.3 °C · Placed by hand",
      );
      expect(screen.queryByRole("button", { name: "Add a peak here" })).not.toBeInTheDocument();
    });

    it("adding a peak says which assigned peak the chosen window replaces", async () => {
      analysis = { ...analysis, steps: ASSIGNED };
      renderPanel();
      await select("Position 2");
      fireEvent.click(screen.getByRole("button", { name: "Add peak" }));
      // Untouched, the transition is left to the temperature range and nothing is replaced.
      expect(screen.getByRole("combobox", { name: "Transition" })).toHaveTextContent(
        "By temperature range",
      );
      expect(screen.queryByText(/saving replaces it/)).not.toBeInTheDocument();
      choose("Transition", "Main 50–85 °C");
      expect(
        screen.getByText(
          "Main is currently the peak at 63.4 °C on this position; saving replaces it.",
        ),
      ).toBeInTheDocument();
    });

    it("By temperature range undoes a transition set by hand", async () => {
      analysis = { ...analysis, steps: ASSIGNED };
      renderPanel();
      const table = await select("Position 2");
      fireEvent.click(within(row(table, "63.4")).getByRole("button", { name: "Use as Tm" }));
      choose("Transition", "By temperature range");
      // The stored reason explained the assignment that is being given up.
      expect(screen.getByLabelText("Reason")).toHaveValue("");
      fireEvent.click(screen.getByRole("button", { name: "Save" }));
      await waitFor(() => expect(writes()).toHaveLength(1));
      expect(writes()[0]).toEqual({
        url: "/api/v1/melting-steps/p1/assignment",
        method: "PUT",
        data: { expected_version: 4, window: null },
      });
    });

    it("an assignment to a name that is no window on the signal says so, with Clear", async () => {
      // "Wide" is a window, but on the other signal.
      analysis = { ...analysis, steps: [{ ...ASSIGNED[0], assigned_window: "Wide" }] };
      renderPanel();
      const table = await select("Position 2");
      const stale = row(table, "63.4");
      expect(
        within(stale).getByText(
          "Set as Tm of 'Wide', which is no longer a transition on this signal",
        ),
      ).toBeInTheDocument();
      expect(within(stale).queryByText(/^Used as Tm/)).not.toBeInTheDocument();
      // It counts as none set: the form opens on the transition whose range holds the peak.
      fireEvent.click(within(stale).getByRole("button", { name: "Use as Tm" }));
      expect(screen.getByRole("combobox", { name: "Transition" })).toHaveTextContent(
        "Main 50–85 °C",
      );
      fireEvent.click(screen.getByRole("button", { name: "Cancel" }));

      fireEvent.click(within(stale).getByRole("button", { name: "Clear" }));
      await waitFor(() => expect(writes()).toHaveLength(1));
      expect(writes()[0]).toEqual({
        url: "/api/v1/melting-steps/p1/assignment",
        method: "PUT",
        data: { expected_version: 4, window: null },
      });
    });
  });

  describe("rejecting one of a position's two counted peaks", () => {
    const HINT = /^The other peak, at /;
    /** Position 2's counted peaks on the shown signal, beside ones that do not
     *  count: a rejected one, one on the other signal, another position's. */
    const withPeaks = (values: number[], windows = WINDOWS) => {
      analysis = {
        ...analysis,
        windows,
        steps: [
          ...values.map((value, i) =>
            step({ id: `q${i}`, well_id: "w2", value, instrument_value: value }),
          ),
          step({ id: "qr", well_id: "w2", value: 70.1, status: "rejected", reason: "noise" }),
          step({ id: "qb", well_id: "w2", channel_key: "b", value: 55.5 }),
          step({ id: "qo", well_id: "w3", value: 61.2 }),
        ],
      };
    };
    const reject = async (value: string) => {
      renderPanel();
      const table = await select("Position 2");
      fireEvent.click(within(row(table, value)).getByRole("button", { name: "Exclude" }));
      expect(screen.getByLabelText("Reason")).toBeInTheDocument();
    };

    it("says the other peak may then be read as the Tm", async () => {
      withPeaks([36.93, 41.2]);
      await reject("41.2");
      expect(
        screen.getByText(
          "The other peak, at 36.93 °C, may then be read as this position's Tm. Exclude it too if it is not a real transition.",
        ),
      ).toBeInTheDocument();
      // A hint only: the save is as it was.
      fireEvent.change(screen.getByLabelText("Reason"), { target: { value: "false mark" } });
      fireEvent.click(screen.getByRole("button", { name: "Save" }));
      await waitFor(() => expect(writes()).toHaveLength(1));
      expect(writes()[0].data).toEqual({
        expected_version: 1,
        status: "rejected",
        value: 41.2,
        reason: "false mark",
      });
    });

    it("says nothing with three counted peaks", async () => {
      withPeaks([36.93, 41.2, 64]);
      await reject("41.2");
      expect(screen.queryByText(HINT)).not.toBeInTheDocument();
    });

    it("says nothing with one counted peak", async () => {
      withPeaks([41.2]);
      await reject("41.2");
      expect(screen.queryByText(HINT)).not.toBeInTheDocument();
    });

    it("says nothing when the signal has no window", async () => {
      // "Wide" is on the other signal.
      withPeaks([36.93, 41.2], [WINDOWS[2]]);
      await reject("41.2");
      expect(screen.queryByText(HINT)).not.toBeInTheDocument();
    });

    it("says nothing in another form of the same peak", async () => {
      withPeaks([36.93, 41.2]);
      renderPanel();
      const table = await select("Position 2");
      fireEvent.click(within(row(table, "41.2")).getByRole("button", { name: "Edit temperature" }));
      expect(screen.queryByText(HINT)).not.toBeInTheDocument();
    });
  });

  describe("Use as Tm is offered only where it can change something", () => {
    /** One transition, Main, on the shown signal. */
    const ONE = [win("Main", 50, 85), WINDOWS[2]];
    const at = (id: string, value: number, over: Partial<MeltingStep> = {}) =>
      step({ id, well_id: "w2", value, instrument_value: value, ...over });
    const pickOn = (wellId: string, x: number) =>
      act(() => plotProps.at(-1)?.onClick?.({ points: [{ x, y: 2, data: { meta: wellId } }] }));
    const barButtons = (kind: "Peak" | "Spot") =>
      within(screen.getByRole("region", { name: `${kind} picked` }))
        .getAllByRole("button")
        .map((b) => b.getAttribute("aria-label") ?? b.textContent);
    const offered = (li: HTMLElement) =>
      within(li).queryByRole("button", { name: "Use as Tm" }) !== null;
    const useAsTm = (li: HTMLElement) =>
      fireEvent.click(within(li).getByRole("button", { name: "Use as Tm" }));
    const transition = () => screen.getByRole("combobox", { name: "Transition" });
    /** The choices of the open form's Transition field; the field is left open. */
    const choices = () => {
      fireEvent.keyDown(transition(), { key: "Enter" });
      return screen.getAllByRole("option").map((o) => o.textContent);
    };

    it("not for the only counted peak inside the only transition, in the list or on the pick bar", async () => {
      analysis = { ...analysis, windows: ONE };
      renderPanel();
      // Position 2: the peak at 64 °C counts, the one at 70.1 °C is excluded.
      const table = await select("Position 2");
      expect(offered(row(table, "64"))).toBe(false);
      expect(offered(row(table, "70.1"))).toBe(false);
      pickOn("w2", 64);
      expect(barButtons("Peak")).toEqual(["Clear the pick", "Exclude", "Move"]);
    });

    it("a spot inside the only transition, on a position with no counted peak, offers only to add a peak", async () => {
      analysis = { ...analysis, windows: ONE, steps: steps.filter((s) => s.well_id !== "w3") };
      renderPanel();
      await select("Position 3");
      pickOn("w3", 60);
      expect(barButtons("Spot")).toEqual(["Clear the pick", "Add a peak here"]);
    });

    it("never without a transition on the signal", async () => {
      // "Wide" is on the other signal; Position 2 has two counted peaks on this one.
      analysis = { ...analysis, windows: [WINDOWS[2]], steps: [at("n1", 55), at("n2", 64)] };
      renderPanel();
      const table = await select("Position 2");
      expect(offered(row(table, "55"))).toBe(false);
      pickOn("w2", 64);
      expect(barButtons("Peak")).toEqual(["Clear the pick", "Mark reviewed", "Exclude", "Move"]);
      pickOn("w2", 75);
      expect(barButtons("Spot")).toEqual(["Clear the pick", "Add a peak here"]);
    });

    it("for each of a position's several counted peaks, and for a peak added beside them", async () => {
      analysis = { ...analysis, windows: ONE, steps: [at("a1", 55), at("a2", 64)] };
      renderPanel();
      const table = await select("Position 2");
      expect(offered(row(table, "55"))).toBe(true);
      expect(offered(row(table, "64"))).toBe(true);
      pickOn("w2", 64);
      expect(barButtons("Peak")).toEqual([
        "Clear the pick",
        "Use as Tm",
        "Mark reviewed",
        "Exclude",
        "Move",
      ]);
      pickOn("w2", 75);
      expect(barButtons("Spot")).toEqual([
        "Clear the pick",
        "Add a peak here",
        "Add and use as Tm",
      ]);
    });

    it("for a peak outside every transition's range, and for a spot outside it; the form starts on the first transition and saves untouched", async () => {
      // The reference's peak at 36.6 °C lies below Main, as the analysis says; Position 3 has no peak.
      analysis = { ...analysis, windows: ONE, steps: [steps[0]], outside_every_window: ["s1"] };
      renderPanel();
      const table = await select("Position 1", "Position 3");
      pickOn("w3", 30);
      expect(barButtons("Spot")).toEqual([
        "Clear the pick",
        "Add a peak here",
        "Add and use as Tm",
      ]);
      pickOn("w1", 36.6);
      expect(barButtons("Peak")).toContain("Use as Tm");
      useAsTm(row(table, "36.6"));
      expect(screen.getByText("Use the peak at 36.6 °C on Position 1 as Tm")).toBeInTheDocument();
      expect(transition()).toHaveTextContent("Main 50–85 °C");
      const save = screen.getByRole("button", { name: "Save" });
      expect(save).toBeEnabled();
      fireEvent.click(save);
      await waitFor(() => expect(writes()).toHaveLength(1));
      expect(writes()[0]).toEqual({
        url: "/api/v1/melting-steps/s1/assignment",
        method: "PUT",
        data: { expected_version: 1, window: "Main" },
      });
    });

    it("for any peak where the signal has more than one transition, each named on the pick bar", async () => {
      analysis = { ...analysis, windows: WINDOWS };
      renderPanel();
      const table = await select("Position 3");
      expect(offered(row(table, "61.2"))).toBe(true);
      pickOn("w3", 61.2);
      expect(barButtons("Peak")).toEqual([
        "Clear the pick",
        "Use as Tm (Low)",
        "Use as Tm (Main)",
        "Mark reviewed",
        "Exclude",
        "Move",
      ]);
    });

    it("for a peak that has its transition set by hand, which By temperature range undoes", async () => {
      analysis = {
        ...analysis,
        windows: ONE,
        steps: [steps[0], at("d1", 64, { assigned_window: "Main" })],
      };
      renderPanel();
      const table = await select("Position 2");
      expect(within(row(table, "64")).getByText("Used as Tm (Main)")).toBeInTheDocument();
      pickOn("w2", 64);
      expect(screen.getByRole("region", { name: "Peak picked" })).toHaveTextContent(
        "Position 2 · peak at 64 °C · From instrument · used as Tm (Main)",
      );
      expect(barButtons("Peak")).toEqual([
        "Clear the pick",
        "Use as Tm",
        "By temperature range",
        "Mark reviewed",
        "Exclude",
        "Move",
      ]);
      useAsTm(row(table, "64"));
      expect(transition()).toHaveTextContent("Main 50–85 °C");
      expect(choices()).toEqual(["Main 50–85 °C", "By temperature range"]);
    });

    it("the form starts on the transition whose range holds the peak, else on the first", async () => {
      analysis = {
        ...analysis,
        windows: WINDOWS,
        steps: [at("f1", 48.1), at("f2", 64), at("f3", 88)],
      };
      renderPanel();
      const table = await select("Position 2");
      for (const [value, starts] of [
        ["48.1", "Low 25–50 °C"],
        ["64", "Main 50–85 °C"],
        ["88", "Low 25–50 °C"],
      ]) {
        useAsTm(row(table, value));
        expect(transition()).toHaveTextContent(starts);
      }
      // No transition was set by hand: there is none to give back to the temperature range.
      expect(choices()).toEqual(["Low 25–50 °C", "Main 50–85 °C"]);
    });
  });

  describe("several counted peaks in the lead transition's range", () => {
    const LINE = /Pick the one to use as Tm\.$/;
    const at = (id: string, value: number, over: Partial<MeltingStep> = {}) =>
      step({ id, well_id: "w2", value, instrument_value: value, ...over });
    /** Main is the only, so the lead, transition; the reference has one peak below it. */
    const withPeaks = (...peaks: MeltingStep[]) => {
      analysis = { ...analysis, windows: [win("Main", 50, 85)], steps: [steps[0], ...peaks] };
    };
    const texts = (table: HTMLElement) =>
      within(table)
        .getAllByRole("listitem")
        .map((li) => li.textContent ?? "");

    it("says how many there are to pick from, above the peaks of the position looked at", async () => {
      // 48.1 °C is below Main's range, and the excluded peak does not count.
      withPeaks(
        at("m1", 48.1),
        at("m2", 55),
        at("m3", 64),
        at("m4", 70.1),
        at("m5", 80, { status: "rejected", reason: "noise" }),
      );
      renderPanel();
      const [reference, line, first, ...rest] = texts(await select("Position 1", "Position 2"));
      expect(reference).toContain("36.6");
      expect(line).toBe("3 peaks here. Pick the one to use as Tm.");
      expect(first).toContain("48.1");
      expect(rest).toHaveLength(4);
    });

    it("counts two", async () => {
      withPeaks(at("m1", 55), at("m2", 64));
      renderPanel();
      expect(texts(await select("Position 2"))[0]).toBe("2 peaks here. Pick the one to use as Tm.");
    });

    it("says nothing with one counted peak in the range", async () => {
      withPeaks(
        at("m1", 48.1),
        at("m2", 64),
        at("m3", 70.1, { status: "rejected", reason: "noise" }),
      );
      renderPanel();
      await select("Position 2");
      expect(screen.queryByText(LINE)).not.toBeInTheDocument();
    });

    it("says nothing once one of them is set by hand", async () => {
      withPeaks(at("m1", 55), at("m2", 64, { assigned_window: "Main" }));
      renderPanel();
      await select("Position 2");
      expect(screen.queryByText(LINE)).not.toBeInTheDocument();
    });

    it("says nothing once a peak outside the range is set by hand as that transition's Tm", async () => {
      withPeaks(at("m1", 48.1, { assigned_window: "Main" }), at("m2", 55), at("m3", 64));
      renderPanel();
      await select("Position 2");
      expect(screen.queryByText(LINE)).not.toBeInTheDocument();
    });

    it("says nothing for a position that is listed but not the one looked at", async () => {
      withPeaks(at("m1", 55), at("m2", 64));
      renderPanel();
      // Position 3, selected last, is the one looked at.
      await select("Position 2", "Position 3");
      expect(screen.queryByText(LINE)).not.toBeInTheDocument();
    });
  });
});

describe("the peaks found in a position's traces", () => {
  /** What the read answers: per signal, [temperature, strength] pairs. */
  const peaksOn = (bySignal: Record<string, [number, number][]>) => ({
    signals: Object.entries(bySignal).map(([channel_key, peaks]) => ({
      channel_key,
      smoothing_window: 3.5,
      candidates: peaks.map(([value, strength]) => ({ value, direction: "rising", strength })),
    })),
  });
  const read = (wellId: string) => `/api/v1/runs/r1/wells/${wellId}/peak-candidates`;
  /** The reads asked for: the position's and the smoothing sent. */
  const reads = () => found.mock.calls.map(([req]) => [req.url, req.params.smoothing_window]);
  /** Every read asked for has come back, or failed. */
  const settled = () =>
    waitFor(() => {
      expect(found).toHaveBeenCalled();
      expect(qc.isFetching()).toBe(0);
    });
  // The traces run from 20 to 90 °C, so a click reaches 1.4 °C.
  const clickTrace = (wellId: string, x: number) =>
    act(() => plotProps.at(-1)?.onClick?.({ points: [{ x, y: 2, data: { meta: wellId } }] }));
  const inBar = (kind: "Peak" | "Spot", name: string) =>
    fireEvent.click(
      within(screen.getByRole("region", { name: `${kind} picked` })).getByRole("button", { name }),
    );
  const value = () => screen.getByLabelText("Value");
  const SNAPPED =
    "Snapped to the peak of the derivative at 72.71 °C. You clicked 72.53 °C: use that.";
  const snapLine = () => screen.queryByText(/^Snapped to/);

  describe("a click on the plot", () => {
    /** Position 3 with its found peaks read, and a spot picked on its trace at 72.53 °C. */
    const spotNear = async (answer: unknown) => {
      found.mockResolvedValue(answer);
      renderPanel();
      await select("Position 3");
      await settled();
      clickTrace("w3", 72.53);
    };

    it("Add a peak here offers the found peak within reach and says so; use that puts the clicked temperature back", async () => {
      await spotNear(
        peaksOn({
          a: [
            [48.1, 40],
            [72.71, 30],
          ],
        }),
      );
      // The spot is where the click landed; the found peak is offered in the form.
      expect(screen.getByRole("region", { name: "Spot picked" })).toHaveTextContent(
        "Position 3 · 72.53 °C",
      );
      inBar("Spot", "Add a peak here");
      expect(value()).toHaveValue(72.71);
      expect(snapLine()?.textContent).toBe(SNAPPED);
      expect(writes()).toHaveLength(0);
      fireEvent.click(screen.getByRole("button", { name: "use that" }));
      expect(value()).toHaveValue(72.53);
      expect(snapLine()).toBeNull();
    });

    it("saves the offered peak as any peak placed by hand, on the form's Save", async () => {
      await spotNear(peaksOn({ a: [[72.71, 30]] }));
      inBar("Spot", "Add a peak here");
      fireEvent.click(screen.getByRole("button", { name: "Save" }));
      await waitFor(() => expect(writes()).toHaveLength(1));
      expect(writes()[0]).toEqual({
        url: "/api/v1/runs/r1/melting-steps",
        method: "POST",
        data: { well_id: "w3", channel_key: "a", value: 72.71 },
      });
    });

    it("Move, then a click, offers the found peak within reach in Edit temperature", async () => {
      found.mockResolvedValue(peaksOn({ a: [[72.71, 30]] }));
      renderPanel();
      await select("Position 2");
      await settled();
      clickTrace("w2", 64.2);
      inBar("Peak", "Move");
      clickTrace("w2", 72.53);
      expect(
        screen.getByText("Edit the temperature of the peak at 64 °C on Position 2"),
      ).toBeInTheDocument();
      expect(value()).toHaveValue(72.71);
      expect(snapLine()?.textContent).toBe(SNAPPED);
      // A later click fills the open form with the temperature clicked, as before.
      clickTrace("w2", 72.4);
      expect(value()).toHaveValue(72.4);
      expect(snapLine()).toBeNull();
      expect(writes()).toHaveLength(0);
    });

    it("uses the clicked temperature when no found peak of the shown signal is within reach", async () => {
      // Signal B has one right there: a click means the peaks of the signal shown.
      await spotNear(peaksOn({ a: [[60, 30]], b: [[72.6, 30]] }));
      inBar("Spot", "Add a peak here");
      expect(value()).toHaveValue(72.53);
      expect(snapLine()).toBeNull();
    });

    it("uses the clicked temperature while the found peaks are loading", async () => {
      found.mockReturnValue(new Promise(() => {}));
      renderPanel();
      await select("Position 3");
      await waitFor(() => expect(found).toHaveBeenCalled());
      clickTrace("w3", 72.53);
      inBar("Spot", "Add a peak here");
      expect(value()).toHaveValue(72.53);
      expect(snapLine()).toBeNull();
    });

    it("uses the clicked temperature when the found peaks could not be loaded", async () => {
      found.mockRejectedValue(new Error("API error: 500"));
      renderPanel();
      await select("Position 3");
      await settled();
      clickTrace("w3", 72.53);
      inBar("Spot", "Add a peak here");
      expect(value()).toHaveValue(72.53);
      expect(snapLine()).toBeNull();
    });

    it("leaves a typed value as typed", async () => {
      found.mockResolvedValue(peaksOn({ a: [[72.71, 30]] }));
      renderPanel();
      await select("Position 3");
      await settled();
      fireEvent.click(screen.getByRole("button", { name: "Add peak" }));
      fireEvent.change(value(), { target: { value: "72.53" } });
      expect(value()).toHaveValue(72.53);
      expect(snapLine()).toBeNull();
      // Typing over an offered peak takes over, and the line does not come back.
      clickTrace("w3", 72.53);
      inBar("Spot", "Add a peak here");
      expect(snapLine()).not.toBeNull();
      fireEvent.change(value(), { target: { value: "72.6" } });
      expect(value()).toHaveValue(72.6);
      expect(snapLine()).toBeNull();
      fireEvent.change(value(), { target: { value: "72.71" } });
      expect(snapLine()).toBeNull();
    });

    it("a spot on another drawn position's trace is offered that position's found peak", async () => {
      found.mockImplementation((req: { url: string }) =>
        Promise.resolve(peaksOn({ a: [[req.url === read("w1") ? 40.2 : 72.71, 30]] })),
      );
      renderPanel();
      await select("Position 3");
      await settled();
      // The reference, drawn beside the selected position.
      clickTrace("w1", 40);
      await waitFor(() => expect(reads()).toContainEqual([read("w1"), undefined]));
      await settled();
      inBar("Spot", "Add a peak here");
      expect(value()).toHaveValue(40.2);
      // The position the results open on, the one then selected, the one picked on: no others.
      expect(reads()).toEqual([
        [read("w2"), undefined],
        [read("w3"), undefined],
        [read("w1"), undefined],
      ]);
    });
  });

  describe("a step on another signal", () => {
    const hint = () => screen.queryByText(/shows a step near/);
    /** Position 3's value in Main (50–85 °C), a window of Signal A unless said, with the flags given. */
    const position3InMain = (flags: string[], channel = "a") => {
      analysis = {
        ...analysis,
        steps: steps.filter((s) => s.well_id !== "w3"),
        windows: [
          {
            ...win("Main", 50, 85, channel),
            positions: [
              { well_id: "w3", tm: null, delta_tm: null, flags, named_by: null, step_id: null },
            ],
          },
        ],
      };
    };

    it("says which signal shows one where the lead window reads No peak, and Show switches to it", async () => {
      position3InMain(["no_step_in_window"]);
      found.mockResolvedValue(peaksOn({ a: [], b: [[72.71, 30]] }));
      renderPanel();
      const list = await select("Position 3");
      expect(within(gridRow("Position 3")).getByText("No peak")).toBeInTheDocument();
      const line = await screen.findByText("Signal B shows a step near 72.7 °C.");
      // Directly under the peaks list, and not naming the only position listed.
      expect(list.nextElementSibling).toContainElement(line);
      expect(list.nextElementSibling).not.toHaveTextContent("Position 3");
      fireEvent.click(screen.getByRole("button", { name: "Show Signal B" }));
      expect(useRunCurves.mock.calls.at(-1)?.[1]).toMatchObject({ channel: "b" });
      expect(screen.getByRole("tab", { name: "Signal B" })).toHaveAttribute(
        "aria-selected",
        "true",
      );
      expect(writes()).toHaveLength(0);
    });

    it("Show moves the signal switch too, after the switch itself was used", async () => {
      // The curves follow the signal asked for; Position 3 reads No peak in Main on Signal B.
      useRunCurves.mockImplementation((_runId: string, params: { channel?: string }) => ({
        data: { ...curves, channel: params.channel ?? "a" },
        isLoading: false,
        isPlaceholderData: false,
      }));
      position3InMain(["no_step_in_window"], "b");
      found.mockResolvedValue(peaksOn({ a: [[72.71, 30]], b: [] }));
      renderPanel();
      await select("Position 3");
      fireEvent.mouseDown(screen.getByRole("tab", { name: "Signal B" }));
      fireEvent.click(await screen.findByRole("button", { name: "Show Signal A" }));
      expect(screen.getByRole("tab", { name: "Signal A" })).toHaveAttribute(
        "aria-selected",
        "true",
      );
      expect(useRunCurves.mock.calls.at(-1)?.[1]).toMatchObject({ channel: "a" });
    });

    it("gives no hint when the window has a peak", async () => {
      position3InMain([]);
      found.mockResolvedValue(peaksOn({ a: [], b: [[72.71, 30]] }));
      renderPanel();
      await select("Position 3");
      await settled();
      expect(hint()).toBeNull();
    });

    it("gives no hint when no other signal has a clear peak inside the window's range", async () => {
      position3InMain(["no_step_in_window"]);
      // One above the window; and the shown signal's own do not count.
      found.mockResolvedValue(peaksOn({ a: [[72.71, 30]], b: [[90, 30]] }));
      renderPanel();
      await select("Position 3");
      await settled();
      expect(hint()).toBeNull();
    });

    it("shows a viewer the hint too", async () => {
      canEdit.value = false;
      position3InMain(["no_step_in_window"]);
      found.mockResolvedValue(peaksOn({ a: [], b: [[72.71, 30]] }));
      renderPanel();
      await select("Position 3");
      expect(await screen.findByText("Signal B shows a step near 72.7 °C.")).toBeInTheDocument();
      expect(screen.getByRole("button", { name: "Show Signal B" })).toBeInTheDocument();
    });

    it("names the position when several are listed: the one selected last", async () => {
      position3InMain(["no_step_in_window"]);
      found.mockResolvedValue(peaksOn({ a: [], b: [[72.71, 30]] }));
      renderPanel();
      await select("Position 2", "Position 3");
      const line = await screen.findByText("Signal B shows a step near 72.7 °C.");
      expect(line.closest("li")).toHaveTextContent(/^Position 3/);
    });

    it("reads a position's found peaks once per smoothing, for the hint and the snap alike", async () => {
      position3InMain(["no_step_in_window"]);
      found.mockResolvedValue(peaksOn({ a: [[72.71, 30]], b: [[72.6, 30]] }));
      renderPanel();
      await select("Position 3");
      expect(await screen.findByText("Signal B shows a step near 72.6 °C.")).toBeInTheDocument();
      clickTrace("w3", 72.53);
      inBar("Spot", "Add a peak here");
      expect(snapLine()?.textContent).toBe(SNAPPED);
      expect(reads()).toEqual([[read("w3"), undefined]]);
      // The Derivative view by itself uses the default smoothing, as the read without one does.
      fireEvent.mouseDown(screen.getByRole("tab", { name: "Derivative" }));
      const field = screen.getByLabelText("Smoothing window");
      expect(reads()).toHaveLength(1);
      fireEvent.change(field, { target: { value: "2" } });
      fireEvent.blur(field);
      await waitFor(() =>
        expect(reads()).toEqual([
          [read("w3"), undefined],
          [read("w3"), 2],
        ]),
      );
    });
  });
});
