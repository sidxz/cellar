import { fireEvent, render, screen, within } from "@testing-library/react";
import { useState } from "react";
import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";

import { MEASURED_CURVE_COLORS } from "@/shared/lib/chart-colors";
import { shortId } from "@/shared/lib/utils";
import { type CurveGroup, type CurveSet, curveSetFromRun } from "../lib/curve-plot";
import { EMPTY_SELECTION, type SelectionState } from "../lib/curve-selection";
import type { RunCurves } from "../types";

const plotCalls: Array<{ data: Array<Record<string, unknown>>; layout: Record<string, unknown> }> =
  [];
vi.mock("@/shared/lib/plotly", () => ({
  Plot: (props: { data: Array<Record<string, unknown>>; layout: Record<string, unknown> }) => {
    plotCalls.push(props);
    return <div data-testid="plot" />;
  },
  getPlotlyGlobal: () => ({ downloadImage: vi.fn() }),
}));

vi.mock("@/shared/hooks/use-workspace-members", () => ({
  useWorkspaceMembers: () => ({ data: [{ user_id: "u1", name: "A. Person" }] }),
}));

import { CurveViewer, type CurveViewerProps } from "./curve-viewer";

const positions = Array.from({ length: 3 }, (_, i) => ({
  well_id: `w${i + 1}`,
  position: `A${i + 1}`,
  row: "A",
  column: i + 1,
  well_type: i === 0 ? "reference" : "sample",
  registration_number: null,
  position_label: `Position ${i + 1}`,
  label: null,
  note: null,
}));

const runCurves: RunCurves = {
  run_id: "r1",
  dose_unit: "uM",
  holder: { kind: "cassette", rows: 1, columns: 3, label: "Holder of 3" },
  positions,
  channels: [
    { key: "a", label: "Signal A", x_unit: "°C", y_unit: null, x_label: null },
    { key: "b", label: "Signal B", x_unit: "°C", y_unit: null, x_label: null },
  ],
  channel: "a",
  curves: positions.map((p) => ({ well_id: p.well_id, x: [20, 21], y: [1, 2], reported: [] })),
  view: "measured",
  window: null,
};

type Callbacks = Pick<
  CurveViewerProps,
  "onChannelChange" | "onViewChange" | "onWindowChange" | "onSelectionChange"
>;

function Harness({
  set = curveSetFromRun(runCurves),
  callbacks,
  ...rest
}: { set?: CurveSet; callbacks: Callbacks } & Partial<CurveViewerProps>) {
  const [selection, setSelection] = useState<SelectionState>(EMPTY_SELECTION);
  const [showReferences, setShowReferences] = useState(false);
  return (
    <CurveViewer
      set={set}
      showReferences={showReferences}
      onShowReferencesChange={setShowReferences}
      selection={selection}
      onSelectionChange={(next) => {
        setSelection(next);
        callbacks.onSelectionChange(next);
      }}
      onChannelChange={callbacks.onChannelChange}
      onViewChange={callbacks.onViewChange}
      onWindowChange={callbacks.onWindowChange}
      exportName="curves"
      {...rest}
    />
  );
}

function callbacks(): Callbacks {
  return {
    onChannelChange: vi.fn(),
    onViewChange: vi.fn(),
    onWindowChange: vi.fn(),
    onSelectionChange: vi.fn(),
  };
}

const RUN_A = "0a1b2c3d-0000-4000-8000-00000000000a";
const RUN_B = "0a1b2c3d-0000-4000-8000-00000000000b";
const UNKNOWN_OPERATOR = "9f8e7d6c-0000-4000-8000-000000000000";
const LABELS: Record<string, string> = {
  a1: "Ref A",
  a2: "Alpha",
  a3: "Gamma",
  b1: "Ref B",
  b2: "Beta",
  b3: "Delta",
};

function runGroup(prefix: "a" | "b"): CurveGroup {
  return {
    key: prefix === "a" ? RUN_A : RUN_B,
    run: {
      runId: prefix === "a" ? RUN_A : RUN_B,
      runDate: prefix === "a" ? "2026-11-03" : "2026-11-04",
      operator: prefix === "a" ? "u1" : UNKNOWN_OPERATOR,
      status: "completed",
      notes: null,
    },
    holder: { kind: "cassette", rows: 1, columns: 3, label: "Holder of 3" },
    positions: [1, 2, 3].map((column) => ({
      well_id: `${prefix}${column}`,
      position: `A${column}`,
      row: "A",
      column,
      well_type: column === 1 ? "reference" : "sample",
      registration_number: null,
      position_label: `Position ${column}`,
      label: LABELS[`${prefix}${column}`],
      note: null,
    })),
  };
}

// Two runs of three positions, position 1 of each a reference; b3 has no curve.
const twoRuns: CurveSet = {
  ...curveSetFromRun(runCurves),
  groups: [runGroup("a"), runGroup("b")],
  curves: new Map(
    ["a1", "a2", "a3", "b1", "b2"].map((id) => [
      id,
      { well_id: id, x: [20, 21], y: [1, 2], reported: [] },
    ]),
  ),
};

/** The slot of a position in the selector of group 0 or 1. */
function slot(group: 0 | 1, column: number) {
  return screen.getAllByRole("button", { name: `Position ${column}` })[group];
}

function lastTraces() {
  return (plotCalls.at(-1)?.data ?? []) as Array<{
    meta: string;
    line: { color: string };
  }>;
}

beforeEach(() => {
  plotCalls.length = 0;
});

// Radix Select opens a listbox that calls scrollIntoView and hasPointerCapture;
// jsdom has neither.
beforeAll(() => {
  if (!Element.prototype.scrollIntoView) Element.prototype.scrollIntoView = vi.fn();
  if (!Element.prototype.hasPointerCapture) {
    Element.prototype.hasPointerCapture = vi.fn(() => false);
  }
  if (!Element.prototype.releasePointerCapture) {
    Element.prototype.releasePointerCapture = vi.fn();
  }
});

/** One holder of `n` sample positions; position i has compound `compoundOf(i)`. */
function compoundSet(n: number, compoundOf: (i: number) => number): CurveSet {
  const ps = Array.from({ length: n }, (_, k) => {
    const i = k + 1;
    const c = compoundOf(i);
    return {
      ...positions[1],
      well_id: `c${i}`,
      position: `A${i}`,
      column: i,
      position_label: `Position ${i}`,
      molecule_id: `m${c}`,
      molecule_name: `ABC-000000${c}`,
    };
  });
  return {
    ...curveSetFromRun(runCurves),
    groups: [
      {
        key: "r1",
        run: null,
        holder: { kind: "cassette", rows: 1, columns: n, label: `Holder of ${n}` },
        positions: ps,
      },
    ],
    curves: new Map(
      ps.map((p) => [p.well_id, { well_id: p.well_id, x: [20, 21], y: [1, 2], reported: [] }]),
    ),
  };
}

function colourOfTrace(id: string) {
  return lastTraces().find((t) => t.meta === id)?.line.color;
}

const series = MEASURED_CURVE_COLORS.dark.series;

describe("CurveViewer colour by group", () => {
  const twoCompounds = compoundSet(3, (i) => (i <= 2 ? 1 : 2));

  it("gives every position of a group the group's colour", () => {
    render(
      <Harness
        callbacks={callbacks()}
        set={twoCompounds}
        initialColour={{ mode: "group", groupBy: "compound" }}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "All" }));
    expect(["c1", "c2", "c3"].map(colourOfTrace)).toEqual([series[0], series[0], series[1]]);
  });

  it("a group keeps its colour when another group is added or removed", () => {
    render(
      <Harness
        callbacks={callbacks()}
        set={twoCompounds}
        initialColour={{ mode: "group", groupBy: "compound" }}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Position 3" }));
    expect(colourOfTrace("c3")).toBe(series[0]);
    fireEvent.click(screen.getByRole("button", { name: "Position 1" }), { metaKey: true });
    expect(colourOfTrace("c1")).toBe(series[1]);
    expect(colourOfTrace("c3")).toBe(series[0]);
    fireEvent.click(screen.getByRole("button", { name: "Position 3" }), { metaKey: true });
    expect(colourOfTrace("c1")).toBe(series[1]);
  });

  it("is unavailable above 8 groups and says why", () => {
    render(
      <Harness
        callbacks={callbacks()}
        set={compoundSet(9, (i) => i)}
        initialColour={{ mode: "group", groupBy: "compound" }}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "All" }));
    expect(screen.getByRole("tab", { name: "By group" })).toBeDisabled();
    expect(screen.getByText("More than 8 groups")).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Highlight" })).toHaveAttribute("aria-selected", "true");
    expect(colourOfTrace("c1")).toBe(MEASURED_CURVE_COLORS.dark.neutral);
  });

  it("groups by run, compound, batch or role as chosen", async () => {
    render(<Harness callbacks={callbacks()} set={twoRuns} initialColour={{ mode: "group" }} />);
    fireEvent.click(slot(0, 1));
    fireEvent.click(slot(0, 2), { metaKey: true });
    fireEvent.click(slot(1, 2), { metaKey: true });
    // By run, the default when the set has runs.
    expect(screen.getByRole("combobox", { name: "Group by" })).toHaveTextContent("Run");
    expect(["a1", "a2", "b2"].map(colourOfTrace)).toEqual([series[0], series[0], series[1]]);
    fireEvent.click(screen.getByRole("combobox", { name: "Group by" }));
    fireEvent.click(await screen.findByRole("option", { name: "Role" }));
    const [a1, a2, b2] = ["a1", "a2", "b2"].map(colourOfTrace);
    expect(a2).toBe(b2);
    expect(a1).not.toBe(a2);
    fireEvent.click(screen.getByRole("combobox", { name: "Group by" }));
    fireEvent.click(await screen.findByRole("option", { name: "Compound" }));
    // None of these has a compound: one group.
    expect(new Set(["a1", "a2", "b2"].map(colourOfTrace)).size).toBe(1);
  });

  it("lets the grouping be changed while By group is unavailable for the current one", async () => {
    render(<Harness callbacks={callbacks()} set={compoundSet(9, (i) => i)} />);
    fireEvent.click(screen.getByRole("button", { name: "All" }));
    expect(screen.getByRole("tab", { name: "By group" })).toBeDisabled();
    fireEvent.click(screen.getByRole("combobox", { name: "Group by" }));
    fireEvent.click(await screen.findByRole("option", { name: "Role" }));
    expect(screen.getByRole("tab", { name: "By group" })).not.toBeDisabled();
  });

  it("starts in the colour mode given by initialColour", () => {
    const { unmount } = render(
      <Harness callbacks={callbacks()} initialColour={{ mode: "distinct" }} />,
    );
    expect(screen.getByRole("tab", { name: /Distinct/ })).toHaveAttribute("aria-selected", "true");
    unmount();
    render(
      <Harness
        callbacks={callbacks()}
        set={twoCompounds}
        initialColour={{ mode: "group", groupBy: "compound" }}
      />,
    );
    expect(screen.getByRole("tab", { name: "By group" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("combobox", { name: "Group by" })).toHaveTextContent("Compound");
  });

  it("lists one legend entry per group", () => {
    render(
      <Harness
        callbacks={callbacks()}
        set={twoCompounds}
        initialColour={{ mode: "group", groupBy: "compound" }}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "All" }));
    const legend = screen.getByTestId("curve-legend");
    expect(
      within(legend)
        .getAllByText(/ABC-/)
        .map((e) => e.textContent),
    ).toEqual(["ABC-0000001", "ABC-0000002"]);
  });
});

describe("CurveViewer run cell", () => {
  it("tells two runs on one date apart in the table, and keeps the date alone otherwise", () => {
    const a = runGroup("a");
    const b = runGroup("b");
    const c = { ...runGroup("b"), key: "run-c" };
    const sameDay: CurveSet = {
      ...twoRuns,
      groups: [
        a,
        { ...b, run: b.run && { ...b.run, runDate: "2026-11-03", notes: "second attempt" } },
        {
          ...c,
          run: c.run && { ...c.run, runId: "run-c", runDate: "2026-11-05" },
          positions: c.positions.map((p) => ({ ...p, well_id: `c-${p.well_id}` })),
        },
      ],
    };
    render(<Harness callbacks={callbacks()} set={sameDay} />);
    for (const s of screen.getAllByRole("button", { name: "Position 2" })) {
      fireEvent.click(s, { metaKey: true });
    }
    const table = screen.getByRole("table");
    const heading = `2026-11-03 · ${shortId(UNKNOWN_OPERATOR)} · Completed · second attempt`;
    // The same text as the selector's heading for that run: the heading and the cell.
    expect(screen.getAllByRole("link", { name: heading })).toHaveLength(2);
    expect(within(table).getByRole("link", { name: heading })).toHaveAttribute(
      "href",
      `/assays/runs/${RUN_B}`,
    );
    expect(within(table).getByRole("link", { name: "2026-11-05" })).toBeInTheDocument();
  });
});

describe("CurveViewer", () => {
  it("reports a signal, view and window change to its parent and keeps the selection", () => {
    const cb = callbacks();
    render(<Harness callbacks={cb} />);
    fireEvent.click(screen.getByRole("button", { name: "Position 2" }));
    expect(cb.onSelectionChange).toHaveBeenCalledTimes(1);
    fireEvent.mouseDown(screen.getByRole("tab", { name: "Signal B" }));
    expect(cb.onChannelChange).toHaveBeenCalledWith("b");
    fireEvent.mouseDown(screen.getByRole("tab", { name: "Derivative" }));
    expect(cb.onViewChange).toHaveBeenCalledWith("derivative");
    const field = screen.getByLabelText("Window");
    fireEvent.change(field, { target: { value: "2" } });
    fireEvent.blur(field);
    expect(cb.onWindowChange).toHaveBeenCalledWith(2);
    expect(cb.onSelectionChange).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("button", { name: "Position 2" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
  });

  it("commits the window on Enter and on blur, not on each keystroke", () => {
    const cb = callbacks();
    render(<Harness callbacks={cb} set={{ ...curveSetFromRun(runCurves), view: "derivative" }} />);
    fireEvent.mouseDown(screen.getByRole("tab", { name: "Derivative" }));
    const field = screen.getByLabelText("Window");
    fireEvent.change(field, { target: { value: "3" } });
    fireEvent.change(field, { target: { value: "3.5" } });
    expect(cb.onWindowChange).not.toHaveBeenCalled();
    fireEvent.keyDown(field, { key: "Enter" });
    expect(cb.onWindowChange).toHaveBeenLastCalledWith(3.5);
    fireEvent.change(field, { target: { value: "4" } });
    expect(cb.onWindowChange).toHaveBeenCalledTimes(1);
    fireEvent.blur(field);
    expect(cb.onWindowChange).toHaveBeenLastCalledWith(4);
    expect(cb.onWindowChange).toHaveBeenCalledTimes(2);
  });

  it("renders what is passed as selectorAction beside the selector", () => {
    render(
      <Harness
        callbacks={callbacks()}
        selectorAction={<button type="button">Side action</button>}
      />,
    );
    const action = screen.getByRole("button", { name: "Side action" });
    const selectorRow = screen
      .getByRole("button", { name: "Position 1" })
      .closest(".flex-1")?.parentElement;
    expect(selectorRow).toContainElement(action);
  });

  it("draws one selector per run under its heading, with a link to the run", () => {
    render(<Harness callbacks={callbacks()} set={twoRuns} />);
    const a = screen.getByRole("link", { name: "2026-11-03 · A. Person · Completed" });
    expect(a).toHaveAttribute("href", `/assays/runs/${RUN_A}`);
    const b = screen.getByRole("link", {
      name: `2026-11-04 · ${shortId(UNKNOWN_OPERATOR)} · Completed`,
    });
    expect(b).toHaveAttribute("href", `/assays/runs/${RUN_B}`);
    expect(screen.getAllByText("0 of 3 selected")).toHaveLength(2);
  });

  it("selects a shift range that crosses two runs", () => {
    render(<Harness callbacks={callbacks()} set={twoRuns} />);
    fireEvent.click(slot(0, 2));
    fireEvent.click(slot(1, 2), { shiftKey: true });
    const pressed = (g: 0 | 1, c: number) => slot(g, c).getAttribute("aria-pressed");
    expect([pressed(0, 1), pressed(0, 2), pressed(0, 3), pressed(1, 1), pressed(1, 2)]).toEqual([
      "false",
      "true",
      "true",
      "true",
      "true",
    ]);
    expect(screen.getByText("4 selected")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Clear" }));
    expect(screen.getByText("0 selected")).toBeInTheDocument();
  });

  it("the filter dims positions in the selector and removes them from the table, and leaves the plot alone", () => {
    render(<Harness callbacks={callbacks()} set={twoRuns} />);
    fireEvent.click(slot(0, 1));
    fireEvent.click(slot(0, 2), { metaKey: true });
    expect(lastTraces()).toHaveLength(2);
    fireEvent.change(screen.getByPlaceholderText("Filter by label, compound, batch or note"), {
      target: { value: "alpha" },
    });
    expect(slot(0, 1)).toBeDisabled();
    expect(slot(0, 2)).toBeEnabled();
    const table = screen.getByRole("table");
    expect(within(table).getByText("Alpha")).toBeInTheDocument();
    expect(within(table).queryByText("Ref A")).not.toBeInTheDocument();
    expect(lastTraces().map((t) => t.meta)).toEqual(["a1", "a2"]);
  });

  it("has a Run column for run groups and none on a set without run information", () => {
    const { unmount } = render(<Harness callbacks={callbacks()} set={twoRuns} />);
    fireEvent.click(slot(1, 2));
    const table = screen.getByRole("table");
    expect(within(table).getByRole("columnheader", { name: "Run" })).toBeInTheDocument();
    expect(within(table).getByRole("link", { name: "2026-11-04" })).toHaveAttribute(
      "href",
      `/assays/runs/${RUN_B}`,
    );
    unmount();
    render(<Harness callbacks={callbacks()} />);
    expect(
      within(screen.getByRole("table")).queryByRole("columnheader", { name: "Run" }),
    ).not.toBeInTheDocument();
  });

  it("lists a drawn position without a curve as not shown, once loading has finished", () => {
    const cb = callbacks();
    const { rerender } = render(<Harness callbacks={cb} set={twoRuns} pending />);
    fireEvent.click(slot(1, 2));
    fireEvent.click(slot(1, 3), { metaKey: true });
    expect(screen.queryByText(/Not shown/)).not.toBeInTheDocument();
    rerender(<Harness callbacks={cb} set={twoRuns} pending={false} />);
    expect(
      screen.getByText("Not shown, no Signal A curve: Position 3 · Delta"),
    ).toBeInTheDocument();
  });

  it("draws a reference position added by the switch in the reference colour in Distinct mode", () => {
    render(<Harness callbacks={callbacks()} set={twoRuns} />);
    fireEvent.click(slot(1, 2));
    fireEvent.mouseDown(screen.getByRole("tab", { name: /Distinct/ }));
    fireEvent.click(screen.getByRole("switch", { name: "Show each run's reference positions" }));
    const traces = lastTraces();
    expect(traces.map((t) => t.meta)).toEqual(["b1", "b2"]);
    expect(traces[0].line.color).toBe(MEASURED_CURVE_COLORS.dark.reference);
    expect(traces[1].line.color).toBe(MEASURED_CURVE_COLORS.dark.series[0]);
    // Not selected, so not a table row.
    expect(within(screen.getByRole("table")).queryByText("Ref B")).not.toBeInTheDocument();
  });

  it("says the curves are loading, not that there are none, until the first answer", () => {
    const loading: CurveSet = { ...twoRuns, curves: new Map() };
    const cb = callbacks();
    const { rerender } = render(<Harness callbacks={cb} set={loading} pending />);
    fireEvent.click(slot(0, 2));
    expect(screen.getByText("Loading curves…")).toBeInTheDocument();
    expect(screen.queryByText(/have no curves/)).not.toBeInTheDocument();
    rerender(<Harness callbacks={cb} set={loading} pending={false} />);
    expect(
      screen.getByText("The selected positions have no curves for this signal."),
    ).toBeInTheDocument();
  });

  it("counts only the selected positions that are loaded", () => {
    // Positions of a run no longer shown stay in the selection the parent holds.
    const gone = Array.from({ length: 9 }, (_, i) => `gone${i}`);
    render(
      <Harness
        callbacks={callbacks()}
        set={twoRuns}
        selection={{ selected: new Set(["a2", ...gone]), anchor: null }}
      />,
    );
    expect(screen.getByText("1 selected")).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /Distinct/ })).not.toBeDisabled();
    expect(screen.queryByText("More than 8 selected")).not.toBeInTheDocument();
  });

  it("asks to narrow the selection above 400 and draws nothing", () => {
    const many = Array.from({ length: 401 }, (_, i) => ({
      ...positions[1],
      well_id: `m${i + 1}`,
      position: `A${i + 1}`,
      column: i + 1,
      position_label: `Position ${i + 1}`,
    }));
    const set: CurveSet = {
      ...curveSetFromRun(runCurves),
      groups: [
        {
          key: "r1",
          run: null,
          holder: { kind: "cassette", rows: 1, columns: 401, label: "Holder of 401" },
          positions: many,
        },
      ],
      curves: new Map(
        many.map((p) => [p.well_id, { well_id: p.well_id, x: [20, 21], y: [1, 2], reported: [] }]),
      ),
    };
    render(<Harness callbacks={callbacks()} set={set} />);
    fireEvent.click(screen.getByRole("button", { name: "All" }));
    expect(
      screen.getByText("More than 400 positions are selected. Narrow the selection to draw them."),
    ).toBeInTheDocument();
    expect(screen.queryByTestId("plot")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "PNG" })).toBeDisabled();
  });
});
