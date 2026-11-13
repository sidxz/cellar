import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
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
vi.mock("@/shared/hooks/use-current-user", () => ({ useCanEdit: () => true }));
vi.mock("./edit-labelling-dialog", () => ({ EditLabellingDialog: () => null }));
vi.mock("@/shared/components/data-grid/data-grid", async () => ({
  DataGrid: (await import("./test-data-grid")).TableGrid,
}));

const api = vi.fn();
vi.mock("@/shared/lib/api/custom-instance", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/shared/lib/api/custom-instance")>()),
  customInstance: (req: unknown) => api(req),
}));

import { ApiError } from "@/shared/lib/api/custom-instance";
import { RunCurvesPanel } from "./run-curves-panel";
import { gridRow } from "./test-data-grid";

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

function change(s: MeltingStep, warning: string | null = null) {
  return { step: s, recalculated: true, compute_warning: warning };
}

beforeEach(() => {
  plotProps.length = 0;
  analysis = {
    run_id: "r1",
    edit_refusal: null,
    steps,
    windows: [],
    step_checks: [],
  };
  useRunCurves.mockReset();
  useRunCurves.mockReturnValue({ data: curves, isLoading: false, isPlaceholderData: false });
  api.mockReset();
  api.mockImplementation((req: { url: string; method: string }) => {
    if (req.url.endsWith("/melting-analysis")) return Promise.resolve(analysis);
    if (req.url.endsWith("/workspace-members"))
      return Promise.resolve([{ user_id: "u1", name: "Ada Lovelace", email: "ada@example.org" }]);
    return Promise.resolve(change(steps[0]));
  });
});

function renderPanel() {
  const qc = new QueryClient({
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
  return screen.findByRole("list", { name: "Melting steps" });
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
    expect(within(s1).getByText("Instrument · Unreviewed")).toBeInTheDocument();
    expect(within(s1).queryByText("B-001")).not.toBeInTheDocument();
    expect(within(s1).queryByText(/was/)).not.toBeInTheDocument();

    const s2 = row(table, "64");
    expect(within(s2).getByText("was 63.5")).toBeInTheDocument();
    expect(within(s2).getByText("shoulder peak")).toBeInTheDocument();
    expect(await within(s2).findByText(/Ada Lovelace/)).toBeInTheDocument();

    const s3 = row(table, "70.1");
    expect(s3.className).toContain("line-through");
    expect(within(s3).getByText("Manual · Rejected")).toBeInTheDocument();
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
      return Promise.resolve(
        change({ ...steps[0], status: "rejected" }, "Recompute the run to update its results."),
      );
    });
    renderPanel();
    const table = await select("Position 1");
    fireEvent.click(within(row(table, "36.6")).getByRole("button", { name: "Reject" }));
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
    fireEvent.click(within(row(table, "64")).getByRole("button", { name: "Correct" }));
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
    fireEvent.click(within(row(table, "36.61")).getByRole("button", { name: "Correct" }));
    expect(screen.getByLabelText("Value")).toHaveValue(36.61);
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(writes()).toHaveLength(1));
    expect(writes()[0].data).toEqual({ expected_version: 1, status: "accepted", value: 36.606635 });
  });

  it("a plot click fills two decimals", async () => {
    renderPanel();
    await select("Position 3");
    fireEvent.click(screen.getByRole("button", { name: "Add step" }));
    plotProps.at(-1)?.onClick?.({ points: [{ x: 32.646001, y: 2 }] });
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

  it("re-sends the current value and reason on Accept", async () => {
    analysis = { ...analysis, steps: [{ ...steps[1], status: "unreviewed" }] };
    renderPanel();
    const table = await select("Position 2");
    fireEvent.click(within(row(table, "64")).getByRole("button", { name: "Accept" }));
    await waitFor(() => expect(writes()).toHaveLength(1));
    expect(writes()[0].data).toEqual({
      expected_version: 2,
      status: "accepted",
      value: 64,
      reason: "shoulder peak",
    });
  });

  it("Accept on a rejected step pre-fills the rejection reason and lets it be cleared", async () => {
    renderPanel();
    const table = await select("Position 2");
    fireEvent.click(within(row(table, "70.1")).getByRole("button", { name: "Accept" }));
    expect(writes()).toHaveLength(0);
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

  it("Mark unreviewed sets an accepted step back, keeping its value and reason", async () => {
    renderPanel();
    const table = await select("Position 2");
    fireEvent.click(within(row(table, "64")).getByRole("button", { name: "Mark unreviewed" }));
    await waitFor(() => expect(writes()).toHaveLength(1));
    expect(writes()[0].data).toEqual({
      expected_version: 2,
      status: "unreviewed",
      value: 64,
      reason: "shoulder peak",
    });
  });

  it("an unreviewed step offers no Mark unreviewed", async () => {
    renderPanel();
    const table = await select("Position 1");
    expect(
      within(row(table, "36.6")).queryByRole("button", { name: "Mark unreviewed" }),
    ).not.toBeInTheDocument();
  });

  it("a plot click fills the open form's value without saving", async () => {
    renderPanel();
    await select("Position 3");
    fireEvent.click(screen.getByRole("button", { name: "Add step" }));
    const onClick = plotProps.at(-1)?.onClick;
    expect(onClick).toBeDefined();
    onClick?.({ points: [{ x: 52.3, y: 2 }] });
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
    const message = "The melting step was changed by someone else. Reload and try again.";
    api.mockImplementation((req: { url: string; method: string }) => {
      if (req.url.endsWith("/melting-analysis")) return Promise.resolve(analysis);
      return Promise.reject(new ApiError(`API error: 409 — ${message}`, 409, { detail: message }));
    });
    renderPanel();
    const table = await select("Position 1");
    fireEvent.click(within(row(table, "36.6")).getByRole("button", { name: "Accept" }));
    expect(await screen.findByText(message)).toBeInTheDocument();
    const reads = () => api.mock.calls.filter(([r]) => r.url.endsWith("/melting-analysis")).length;
    const before = reads();
    fireEvent.click(screen.getByRole("button", { name: "Reload" }));
    await waitFor(() => expect(reads()).toBe(before + 1));
    await waitFor(() => expect(screen.queryByText(message)).not.toBeInTheDocument());
  });

  it("hides actions and shows the refusal on a completed run", async () => {
    const refusal = "Melting steps can be changed only while the run is draft or in progress";
    analysis = { ...analysis, edit_refusal: refusal };
    renderPanel();
    const table = await select("Position 1");
    expect(screen.getByText(refusal)).toBeInTheDocument();
    for (const name of ["Accept", "Reject", "Correct", "Mark unreviewed", "Add step"]) {
      expect(screen.queryByRole("button", { name })).not.toBeInTheDocument();
    }
    expect(within(table).getByText("36.6")).toBeInTheDocument();
  });
});
