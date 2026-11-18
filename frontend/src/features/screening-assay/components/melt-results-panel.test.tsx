import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { type ReactNode, useState } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { formatDateTime } from "@/shared/lib/format-date";
import type { CurvePosition } from "../lib/curve-plot";
import { EMPTY_SELECTION, type SelectionState } from "../lib/curve-selection";
import type { ApplicableRule } from "../lib/melt-hits";
import type { MeltWindow, MeltingAnalysis, MeltingStep } from "../types";

vi.mock("@/shared/components/chemistry/structure-thumbnail", () => ({
  StructureThumbnail: ({ smiles }: { smiles: string }) => (
    <div data-testid="structure" data-smiles={smiles} />
  ),
}));

const plots: { data: Record<string, any>[]; onClick?: (e: unknown) => void }[] = [];
vi.mock("@/shared/lib/plotly", () => ({
  Plot: (p: (typeof plots)[number]) => {
    plots.push(p);
    return <div data-testid="plot" />;
  },
}));

vi.mock("@/shared/components/data-grid/data-grid", async () => ({
  DataGrid: (await import("../test/test-data-grid")).TableGrid,
}));
vi.mock("@/shared/hooks/use-workspace-members", () => ({
  useWorkspaceMembers: () => ({
    data: [{ user_id: "u1", name: "Ada Lovelace", email: "ada@lab.org" }],
  }),
}));

import { MeltResultsPanel } from "./melt-results-panel";

function pos(id: string, over: Record<string, unknown> = {}) {
  return {
    well_id: id,
    position_label: `Capillary ${id}`,
    row: "A",
    column: 1,
    label: null,
    well_type: "sample",
    registration_number: "",
    molecule_id: null,
    batch_id: null,
    batch_number: null,
    smiles: null,
    dose: null,
    ...over,
  } as unknown as CurvePosition;
}
const positions = [
  pos("r1", { well_type: "reference", label: "MadR" }),
  pos("s1", {
    registration_number: "CC-014538",
    molecule_id: "m1",
    batch_number: "CC-014538-001",
    smiles: "CCO",
    dose: 6.25,
  }),
  pos("s2", { label: "16:0-CoA", dose: 10 }),
  pos("s3", { registration_number: "CC-000002", molecule_id: "m2" }),
  pos("s4", { label: "Lipid X" }),
];
/** `stepId`: the peak the server says gave the Tm (a peak's id is its position's). */
const wp = (
  id: string,
  tm: number | null,
  d: number | null,
  flags: string[] = [],
  stepId: string | null = null,
) => ({
  well_id: id,
  tm,
  delta_tm: d,
  flags,
  named_by: stepId ? "range" : null,
  step_id: stepId,
});
const win = (window: string, channel: string, low: number, high: number, ps: unknown[]) =>
  ({
    window,
    channel_key: channel,
    low,
    high,
    reference_tm: 71.3,
    reference_count: 1,
    flags: [],
    positions: ps,
  }) as unknown as MeltWindow;
const step = (well: string, value: number, status: string, channel = "a") =>
  ({ id: well, well_id: well, channel_key: channel, value, status }) as unknown as MeltingStep;

const analysis = {
  run_id: "run",
  edit_refusal: null,
  windows: [
    win("Main", "a", 50, 85, [
      wp("r1", 71.3, 0, [], "r1"),
      wp("s1", 62.8, -8.5, [], "s1"),
      wp("s2", 74.3, 3.0, [], "s2"),
      wp("s3", 70.3, -1.0, [], "s3"),
      wp("s4", null, null, ["no_step_in_window"]),
    ]),
    win("Low", "a", 30, 50, [
      wp("r1", 40, 0),
      wp("s1", 42, 2.0),
      wp("s2", 39, -1.0),
      wp("s3", 30, -10),
    ]),
    win("High", "b", 60, 90, [wp("r1", 70, 0)]),
    win("Low", "b", 30, 50, [wp("r1", 40, 0)]),
  ],
  steps: [
    step("r1", 71.3, "accepted"),
    step("s1", 62.8, "accepted"),
    step("s2", 74.3, "accepted"),
    step("s3", 70.3, "unreviewed"),
  ],
  step_checks: [],
  outside_every_window: [],
} as unknown as MeltingAnalysis;

/** The run's rule "ΔTm (Main) outside −2 to 2": s1 (−8.5) and s2 (+3.0) are hits. */
const OUTSIDE_MAIN: ApplicableRule[] = [
  {
    rule: { readout_name: "ΔTm (Main)", operator: "not_between", value: [-2, 2] },
    window: "Main",
    measure: "delta_tm",
  },
];
const HITS = new Set(["s1", "s2"]);

function Harness({
  channel = "a",
  onChange = () => {},
  onLead,
  data = analysis,
  hits = HITS,
  applicable = OUTSIDE_MAIN,
  at = positions,
  onNamePeaks,
  workspace,
}: {
  /** The run's positions. */
  at?: CurvePosition[];
  onNamePeaks?: () => void;
  channel?: string;
  onChange?: (s: SelectionState) => void;
  onLead?: (w: string | null) => void;
  data?: MeltingAnalysis;
  hits?: ReadonlySet<string>;
  applicable?: ApplicableRule[];
  workspace?: ReactNode;
}) {
  const [selection, setSelection] = useState<SelectionState>(EMPTY_SELECTION);
  return (
    <MeltResultsPanel
      analysis={data}
      positions={at}
      channel={channel}
      doseUnit="µM"
      selection={selection}
      onSelectionChange={(s) => {
        onChange(s);
        setSelection(s);
      }}
      onLeadWindowChange={onLead}
      hits={hits}
      applicable={applicable}
      onNamePeaks={onNamePeaks}
      workspace={workspace}
    />
  );
}

const table = () => screen.getByRole("table");
const bodyIds = () =>
  within(table())
    .getAllByRole("row")
    .flatMap((r) => r.getAttribute("data-row-id") ?? []);
const row = (id: string) => {
  const el = table().querySelector(`[data-row-id="${id}"]`);
  if (!el) throw new Error(`row ${id} not shown`);
  return el as HTMLElement;
};
/** What a row's Status cell (the last) reads. */
const status = (id: string) => [...(row(id) as HTMLTableRowElement).cells].at(-1)?.textContent;
/** The counts of the line above the grid, each a filter. */
const stripButtons = () =>
  within(screen.getByText(/^Reference MadR/).parentElement as HTMLElement)
    .getAllByRole("button")
    .map((b) => b.textContent);
const tabNames = () =>
  within(screen.getByRole("tablist", { name: "Transition" }))
    .getAllByRole("tab")
    .map((t) => t.textContent);

const lastSelected = (fn: ReturnType<typeof vi.fn>) => [
  ...(fn.mock.lastCall?.[0] as SelectionState).selected,
];

describe("MeltResultsPanel", () => {
  it("lists only the windows of the current signal and keeps the chosen one across a signal change", () => {
    const onLead = vi.fn();
    const { rerender } = render(<Harness channel="a" onLead={onLead} />);
    expect(tabNames()).toEqual(["Main 50–85 °C", "Low 30–50 °C", "Compare"]);
    expect(onLead).toHaveBeenLastCalledWith("Main");
    fireEvent.mouseDown(screen.getByRole("tab", { name: "Low 30–50 °C" }));
    expect(onLead).toHaveBeenLastCalledWith("Low");
    rerender(<Harness channel="b" onLead={onLead} />);
    expect(tabNames()).toEqual(["High 60–90 °C", "Low 30–50 °C", "Compare"]);
    expect(screen.getByRole("tab", { name: "Low 30–50 °C" })).toHaveAttribute(
      "aria-selected",
      "true",
    );
    // Compare keeps the lead window.
    fireEvent.mouseDown(screen.getByRole("tab", { name: "Compare" }));
    expect(onLead).toHaveBeenLastCalledWith("Low");
  });

  it("lists positions and the no-window sentence when the signal has no window", () => {
    const onLead = vi.fn();
    render(<Harness channel="c" onLead={onLead} />);
    expect(screen.getByText("No transition named on this signal.")).toBeInTheDocument();
    // A viewer is offered nothing to do about it.
    expect(screen.queryByRole("button", { name: /set up windows/i })).not.toBeInTheDocument();
    expect(bodyIds()).toEqual(["r1", "s1", "s2", "s3", "s4"]);
    expect(within(table()).queryByText("Tm (°C)")).not.toBeInTheDocument();
    expect(screen.queryByRole("tablist", { name: "Transition" })).not.toBeInTheDocument();
    expect(onLead).toHaveBeenLastCalledWith(null);
  });

  describe("setting up windows", () => {
    const setUp = () => screen.queryAllByRole("button", { name: "Name transitions" });
    /** The analysis with one more counted peak, outside every window of signal a. */
    const outside = (well: string, channel = "a") =>
      ({
        ...analysis,
        steps: [...analysis.steps, { ...step(well, 95, "unreviewed", channel), id: "o1" }],
        outside_every_window: ["o1"],
      }) as MeltingAnalysis;

    it("is a button in the header, and a link in the note, when the signal has no window", () => {
      const onNamePeaks = vi.fn();
      render(<Harness channel="c" onNamePeaks={onNamePeaks} />);
      const header = screen.getByRole("heading", { name: "Results" }).parentElement as HTMLElement;
      const button = within(header).getByRole("button", { name: "Name transitions" });
      expect(button).toHaveTextContent(/^Name transitions$/);
      expect(button).toHaveAttribute("data-variant", "outline");
      fireEvent.click(button);
      expect(onNamePeaks).toHaveBeenCalledTimes(1);

      const note = screen.getByText(/^No transition named on this signal\./);
      expect(note).toHaveTextContent(/^No transition named on this signal\. Name transitions\.$/);
      const link = within(note).getByRole("button", { name: "Name transitions" });
      expect(link).toHaveTextContent(/^Name transitions$/);
      fireEvent.click(link);
      expect(onNamePeaks).toHaveBeenCalledTimes(2);
      expect(screen.queryByText(/Setup tab/)).not.toBeInTheDocument();
    });

    it("is a quiet Edit after the Window switch when the windows hold the reference's peaks", () => {
      const onNamePeaks = vi.fn();
      render(<Harness onNamePeaks={onNamePeaks} />);
      // One control, and it is not the outlined button.
      expect(setUp()).toHaveLength(1);
      const edit = setUp()[0];
      expect(edit).toHaveTextContent(/^Edit$/);
      expect(edit).toHaveAttribute("data-variant", "link");
      const precedes = (a: Element, b: Element) =>
        !!(a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING);
      expect(precedes(screen.getByRole("tablist", { name: "Transition" }), edit)).toBe(true);
      expect(precedes(edit, screen.getByRole("tablist", { name: "View" }))).toBe(true);
      fireEvent.click(edit);
      expect(onNamePeaks).toHaveBeenCalledTimes(1);
      expect(screen.queryByText(/No transition named/)).not.toBeInTheDocument();
    });

    it("is the button again when a reference has a peak outside every window", () => {
      render(<Harness data={outside("r1")} onNamePeaks={() => {}} />);
      expect(setUp()).toHaveLength(1);
      expect(setUp()[0]).toHaveTextContent(/^Name transitions$/);
      expect(screen.queryByRole("button", { name: "Edit" })).not.toBeInTheDocument();
    });

    it("stays the Edit for a sample's stray peak, or a reference's on another signal", () => {
      const sample = render(<Harness data={outside("s1")} onNamePeaks={() => {}} />);
      expect(setUp().map((b) => b.textContent)).toEqual(["Edit"]);
      sample.unmount();
      render(<Harness data={outside("r1", "b")} onNamePeaks={() => {}} />);
      expect(setUp().map((b) => b.textContent)).toEqual(["Edit"]);
    });

    it("is not offered to a viewer, with or without a window", () => {
      const { rerender } = render(<Harness />);
      expect(setUp()).toHaveLength(0);
      expect(screen.queryByText("Edit")).not.toBeInTheDocument();
      rerender(<Harness channel="c" />);
      expect(setUp()).toHaveLength(0);
      expect(screen.getByText("No transition named on this signal.")).toHaveTextContent(
        /^No transition named on this signal\.$/,
      );
    });
  });

  it("shows signed ΔTm in direction colour without a tint, and the status chip", () => {
    render(<Harness />);
    const delta = (id: string, text: string) => within(row(id)).getByText(text).closest("td");
    expect(delta("s1", "−8.5")).toHaveClass("text-red-700", "font-semibold");
    expect(delta("s2", "+3.0")).toHaveClass("text-blue-700", "font-semibold");
    expect(delta("s2", "+3.0")?.className).not.toMatch(/bg-/);
    expect(delta("s3", "−1.0")).toHaveClass("text-muted-foreground");
    // A peak nobody has reviewed (s3's) gives its value with no word about review.
    expect(status("s3")).toBe("");
    expect(status("s1")).toBe("Reviewed");
    expect(status("s4")).toBe("No peak");
    // The peak that gave the reference its Tm in the shown window is accepted.
    expect(status("r1")).toBe("Reference · Reviewed");
    expect(within(row("r1")).getByText("—")).toBeInTheDocument();
    // Identity: registered links to the compound with the batch suffix; unregistered
    // reads plain, the tag in its title.
    expect(within(row("s1")).getByRole("link", { name: "CC-014538" })).toHaveAttribute(
      "href",
      "/compounds/m1",
    );
    expect(within(row("s1")).getByText("·001")).toBeInTheDocument();
    expect(within(row("s2")).getByTitle("16:0-CoA (unregistered)")).toHaveTextContent(/^16:0-CoA$/);
    expect(within(row("s2")).queryByText("unregistered")).toBeNull();
    // Samples by |ΔTm|, missing last; references pinned first.
    expect(bodyIds()).toEqual(["r1", "s1", "s2", "s3", "s4"]);
  });

  it("strip counts filter the grid and a second click clears", () => {
    render(<Harness />);
    expect(screen.getByText("Reference MadR 71.3 °C (n=1)")).toBeInTheDocument();
    expect(screen.getByText("Main", { selector: "span" })).toBeInTheDocument();
    expect(screen.queryByText(/of 4 samples/)).toBeNull();
    // Nothing counts, or filters to, the peaks nobody has reviewed (s3's).
    expect(stripButtons()).toEqual([
      "Needs a look 1",
      "Hits 2",
      "1 up",
      "1 down",
      "Not evaluated 1",
    ]);
    expect(screen.queryByText(/provisional/i)).toBeNull();
    expect(screen.getByRole("button", { name: "Hits 2" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "1 up" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "1 down" })).toBeInTheDocument();
    expect(screen.queryByLabelText("Shift threshold (°C)")).toBeNull();
    const needs = screen.getByRole("button", { name: "Needs a look 1" });
    fireEvent.click(needs);
    expect(needs).toHaveAttribute("aria-pressed", "true");
    expect(bodyIds()).toEqual(["r1", "s4"]);
    expect(screen.getByText("1 of 4 samples")).toBeInTheDocument();
    fireEvent.click(needs);
    expect(needs).toHaveAttribute("aria-pressed", "false");
    expect(bodyIds()).toEqual(["r1", "s1", "s2", "s3", "s4"]);
    fireEvent.click(screen.getByRole("button", { name: "1 down" }));
    expect(bodyIds()).toEqual(["r1", "s1"]);
  });

  it("row click selects; shift selects a range in display order; ctrl toggles", () => {
    const onChange = vi.fn();
    render(<Harness onChange={onChange} />);
    const last = () => {
      const s = onChange.mock.lastCall?.[0] as SelectionState;
      return { selected: [...s.selected].sort(), anchor: s.anchor };
    };
    fireEvent.click(row("s2"));
    expect(last()).toEqual({ selected: ["s2"], anchor: "s2" });
    expect(row("s2").className).toContain("bg-primary/10!");
    fireEvent.click(row("s4"), { shiftKey: true });
    expect(last()).toEqual({ selected: ["s2", "s3", "s4"], anchor: "s2" });
    fireEvent.click(row("r1"), { shiftKey: true });
    expect(last()).toEqual({ selected: ["r1", "s1", "s2"], anchor: "s2" });
    fireEvent.click(row("s4"), { ctrlKey: true });
    expect(last()).toEqual({ selected: ["r1", "s1", "s2", "s4"], anchor: "s4" });
    fireEvent.click(row("s1"), { metaKey: true });
    expect(last()).toEqual({ selected: ["r1", "s2", "s4"], anchor: "s1" });
    // A click on the compound link does not select.
    const calls = onChange.mock.calls.length;
    const link = within(row("s1")).getByRole("link");
    link.addEventListener("click", (e) => e.preventDefault());
    fireEvent.click(link);
    expect(onChange.mock.calls.length).toBe(calls);
  });

  it("compare shows a column pair per window and sorts by the largest shift", () => {
    render(<Harness hits={new Set(["s1", "s2", "s3"])} />);
    fireEvent.mouseDown(screen.getByRole("tab", { name: "Compare" }));
    const t = within(table());
    expect(t.getByRole("columnheader", { name: "Main" })).toBeInTheDocument();
    expect(t.getByRole("columnheader", { name: "Low" })).toBeInTheDocument();
    expect(t.getAllByRole("columnheader", { name: "Tm (°C)" })).toHaveLength(2);
    expect(t.getAllByRole("columnheader", { name: "ΔTm (°C)" })).toHaveLength(2);
    expect(bodyIds()).toEqual(["r1", "s3", "s1", "s2", "s4"]);
    // Worst status across windows: unreviewed in Main beats reviewed in Low, and reads as nothing.
    expect(status("s3")).toBe("");
    expect(within(row("s3")).getByText("−10.0").closest("td")).toHaveClass("text-red-700");
    // The strip names what it counts and gives each window's reference.
    expect(screen.getByText("All transitions", { selector: "span" })).toBeInTheDocument();
    expect(screen.getByText("Reference MadR · Main 71.3 °C · Low 71.3 °C")).toBeInTheDocument();
  });

  it("compare says which window has no reference", () => {
    const data = {
      ...analysis,
      windows: analysis.windows.map((w) =>
        w.window === "Low" && w.channel_key === "a" ? { ...w, reference_tm: null } : w,
      ),
    } as MeltingAnalysis;
    render(<Harness data={data} />);
    fireEvent.mouseDown(screen.getByRole("tab", { name: "Compare" }));
    const strip = screen.getByText(/^Reference MadR · Main 71\.3 °C · Low/);
    expect(within(strip).getByText("No reference")).toBeInTheDocument();
  });

  it("tint and counts follow the run's hits, not a threshold", () => {
    // s3 (−1.0) is called a hit; s2 (+3.0) is not.
    render(<Harness hits={new Set(["s1", "s3"])} />);
    expect(within(row("s3")).getByText("−1.0").closest("td")).toHaveClass("text-red-700");
    expect(within(row("s2")).getByText("+3.0").closest("td")).toHaveClass("text-muted-foreground");
    expect(within(row("s3")).getByText("Hit")).toBeInTheDocument();
    expect(within(row("s2")).queryByText("Hit")).toBeNull();
    expect(screen.getByRole("button", { name: "2 down" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Hits 2" }));
    expect(bodyIds()).toEqual(["r1", "s1", "s3"]);
  });

  it("without a rule on Tm or ΔTm the strip shows no hit counts", () => {
    render(<Harness hits={new Set()} applicable={[]} />);
    expect(screen.queryByRole("button", { name: /^Hits/ })).toBeNull();
    expect(screen.queryByRole("button", { name: /up$/ })).toBeNull();
    expect(within(row("s2")).getByText("+3.0").closest("td")).toHaveClass("text-muted-foreground");
  });

  it("an unreviewed reference reads Reference, and nothing asks for its review", () => {
    const data = {
      ...analysis,
      steps: analysis.steps.map((s) => (s.well_id === "r1" ? step("r1", 71.3, "unreviewed") : s)),
    } as MeltingAnalysis;
    render(<Harness data={data} />);
    expect(status("r1")).toBe("Reference");
    expect(screen.queryByText(/not reviewed/i)).toBeNull();
    expect(stripButtons()).toEqual([
      "Needs a look 1",
      "Hits 2",
      "1 up",
      "1 down",
      "Not evaluated 1",
    ]);
  });

  it("an unreviewed value still warns that its peaks differ from the reference's", () => {
    const data = {
      ...analysis,
      step_checks: [{ channel_key: "a", differs: ["s3"], references_differ: false }],
    } as unknown as MeltingAnalysis;
    render(<Harness data={data} />);
    expect(status("s3")).toBe("");
    expect(
      within(row("s3")).getByRole("img", { name: "Different number of peaks than the reference" }),
    ).toBeInTheDocument();
  });

  it("the search box finds a sample by label, position or batch", () => {
    render(<Harness />);
    const search = screen.getByPlaceholderText("Find sample, position or batch");
    fireEvent.change(search, { target: { value: "16:0" } });
    expect(bodyIds()).toEqual(["r1", "s2"]);
    fireEvent.change(search, { target: { value: "Capillary s3" } });
    expect(bodyIds()).toEqual(["r1", "s3"]);
    fireEvent.change(search, { target: { value: "001" } });
    expect(bodyIds()).toEqual(["r1", "s1"]);
    // Numbers in the value columns are not searched.
    fireEvent.change(search, { target: { value: "8.5" } });
    expect(bodyIds()).toEqual(["r1"]);
  });

  it("Enter or Space on a focused row selects it, with Shift for a range", () => {
    const onChange = vi.fn();
    render(<Harness onChange={onChange} />);
    fireEvent.keyDown(row("s2"), { key: "Enter" });
    expect(lastSelected(onChange)).toEqual(["s2"]);
    fireEvent.keyDown(row("s3"), { key: " ", shiftKey: true });
    expect(lastSelected(onChange).sort()).toEqual(["s2", "s3"]);
    const calls = onChange.mock.calls.length;
    fireEvent.keyDown(row("s4"), { key: "a" });
    expect(onChange.mock.calls.length).toBe(calls);
  });

  it("marks a Tm named by assignment and says who, when, why and where it falls", () => {
    const assigned = {
      id: "a1",
      well_id: "s1",
      channel_key: "a",
      value: 42,
      status: "accepted",
      assigned_window: "Main",
      assignment_reason: "main transition, shifted low",
      assigned_by: "u1",
      assigned_at: "2026-11-13T10:00:00Z",
    } as unknown as MeltingStep;
    const named = (value: number, reason: string | null) =>
      ({
        ...analysis,
        windows: analysis.windows.map((w) =>
          w.window === "Main" && w.channel_key === "a"
            ? {
                ...w,
                positions: w.positions.map((p) =>
                  p.well_id === "s1"
                    ? { ...p, tm: value, named_by: "assignment", step_id: "a1" }
                    : p,
                ),
              }
            : w,
        ),
        steps: [...analysis.steps, { ...assigned, value, assignment_reason: reason }],
      }) as MeltingAnalysis;
    const mark = () => within(row("s1")).getByRole("img", { name: "Peak chosen by hand" });

    const { unmount } = render(<Harness data={named(42, "main transition, shifted low")} />);
    // Named by range: no marker.
    expect(within(row("s2")).queryByRole("img", { name: "Peak chosen by hand" })).toBeNull();
    expect(mark().closest("td")).toHaveTextContent("42.0");
    fireEvent.focus(mark());
    const tip = screen.getByRole("tooltip");
    expect(tip).toHaveTextContent(
      `Chosen as Tm by Ada Lovelace · ${formatDateTime("2026-11-13T10:00:00Z")}`,
    );
    expect(tip).toHaveTextContent("main transition, shifted low");
    expect(tip).toHaveTextContent("By temperature range: in Low");
    unmount();

    render(<Harness data={named(92.4, null)} />);
    fireEvent.focus(mark());
    expect(screen.getByRole("tooltip")).toHaveTextContent(
      /^Chosen as Tm by Ada Lovelace · [^·]+By temperature range: outside every transition's range$/,
    );
  });

  it("No peak says which peaks lie outside every window", () => {
    const outside = (...values: number[]) =>
      ({
        ...analysis,
        steps: [
          ...analysis.steps,
          ...values.map((v, i) => ({ ...step("s4", v, "unreviewed"), id: `o${i}` })),
        ],
        outside_every_window: values.map((_, i) => `o${i}`),
      }) as MeltingAnalysis;
    const noPeak = () => within(row("s4")).getByText("No peak");

    const { unmount } = render(<Harness />);
    fireEvent.focus(noPeak());
    expect(screen.queryByRole("tooltip")).toBeNull();
    unmount();

    const one = render(<Harness data={outside(92.44)} />);
    fireEvent.focus(noPeak());
    expect(screen.getByRole("tooltip")).toHaveTextContent(
      "Peak at 92.4 °C is outside every transition's range. Pick it on the graph to use it as Tm.",
    );
    one.unmount();

    render(<Harness data={outside(92.44, 20.5)} />);
    fireEvent.focus(noPeak());
    expect(screen.getByRole("tooltip")).toHaveTextContent(
      "Peaks at 20.5 °C and 92.4 °C are outside every transition's range. Pick one on the graph to use it as Tm.",
    );
  });

  it("Not evaluated counts the samples a rule has no value for and filters to them", () => {
    render(<Harness />);
    // s4 has no ΔTm in Main, so the rule on it cannot be judged.
    const button = screen.getByRole("button", { name: "Not evaluated 1" });
    const hits = screen.getByRole("button", { name: "Hits 2" });
    expect(hits.compareDocumentPosition(button) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    fireEvent.click(button);
    expect(button).toHaveAttribute("aria-pressed", "true");
    expect(bodyIds()).toEqual(["r1", "s4"]);
    expect(screen.getByText("1 of 4 samples")).toBeInTheDocument();
    // The shift plot follows the same filter: s4 has no ΔTm to draw.
    fireEvent.mouseDown(screen.getByRole("tab", { name: "Shift plot" }));
    expect(plots[plots.length - 1].data[0].customdata).toEqual([]);
  });

  it("shows no Not evaluated count without a rule, or when every sample has its value", () => {
    const { unmount } = render(<Harness hits={new Set()} applicable={[]} />);
    expect(screen.queryByRole("button", { name: /^Not evaluated/ })).toBeNull();
    unmount();
    const complete = {
      ...analysis,
      windows: analysis.windows.map((w) =>
        w.window === "Main" && w.channel_key === "a"
          ? { ...w, positions: w.positions.map((p) => (p.well_id === "s4" ? wp("s4", 70, 1) : p)) }
          : w,
      ),
    } as MeltingAnalysis;
    render(<Harness data={complete} />);
    expect(screen.queryByRole("button", { name: /^Not evaluated/ })).toBeNull();
  });

  it("without a reference, Not evaluated counts each sample once across the windows", () => {
    const noReference = {
      ...analysis,
      windows: analysis.windows.map((w) => ({
        ...w,
        reference_tm: null,
        reference_count: 0,
        positions: w.positions
          .filter((p) => p.well_id !== "r1")
          .map((p) => ({ ...p, delta_tm: null, flags: ["no_reference_value"] })),
      })),
    } as MeltingAnalysis;
    const rules: ApplicableRule[] = [
      ...OUTSIDE_MAIN,
      {
        rule: { readout_name: "ΔTm (Low)", operator: "gt", value: 1 },
        window: "Low",
        measure: "delta_tm",
      },
    ];
    render(
      <Harness
        data={noReference}
        at={positions.filter((p) => p.well_id !== "r1")}
        hits={new Set()}
        applicable={rules}
      />,
    );
    fireEvent.mouseDown(screen.getByRole("tab", { name: "Compare" }));
    fireEvent.click(screen.getByRole("button", { name: "Not evaluated 4" }));
    expect(bodyIds()).toEqual(["s1", "s2", "s3", "s4"]);
    expect(screen.getByText("4 of 4 samples")).toBeInTheDocument();
  });

  it("focusing a registration number shows the structure", () => {
    render(<Harness />);
    expect(screen.queryByTestId("structure")).toBeNull();
    act(() => within(row("s1")).getByRole("link", { name: "CC-014538" }).focus());
    expect(screen.getAllByTestId("structure").length).toBeGreaterThan(0);
  });
});

describe("the Concentration column", () => {
  const headers = () =>
    within(table())
      .getAllByRole("columnheader")
      .flatMap((h) => h.textContent || []);
  const withDoses = (doses: Record<string, number>) =>
    positions.map((p) => ({ ...p, dose: doses[p.well_id] ?? null }));

  it("is not shown when no position of the run has a concentration", () => {
    render(<Harness at={withDoses({})} />);
    expect(headers()).toEqual(["Sample", "Position", "Tm (°C)", "ΔTm (°C)", "Hit", "Status"]);
  });

  it("is shown when one position has a concentration", () => {
    render(<Harness at={withDoses({ s2: 10 })} />);
    expect(headers()).toEqual([
      "Sample",
      "Position",
      "Conc. (µM)",
      "Tm (°C)",
      "ΔTm (°C)",
      "Hit",
      "Status",
    ]);
    expect((row("s2") as HTMLTableRowElement).cells[2]).toHaveTextContent(/^10$/);
    expect((row("s1") as HTMLTableRowElement).cells[2]).toHaveTextContent(/^$/);
  });

  it("stays while a filter hides the only positions that have one", () => {
    // s2 (+3.0, a hit up) has the run's only concentration; "1 down" leaves s1.
    render(<Harness at={withDoses({ s2: 10 })} />);
    fireEvent.click(screen.getByRole("button", { name: "1 down" }));
    expect(bodyIds()).toEqual(["r1", "s1"]);
    expect(headers()).toContain("Conc. (µM)");
  });
});

describe("the Structures switch", () => {
  beforeEach(() => localStorage.clear());
  const toggle = () => screen.getByRole("button", { name: "Structures" });
  const drawn = (id: string) => within(row(id)).queryAllByTestId("structure").length;

  it("draws the structure in the Sample cell of each registered compound that has one", () => {
    render(<Harness />);
    expect(toggle()).toHaveAttribute("aria-pressed", "false");
    expect(screen.queryByTestId("structure")).toBeNull();

    fireEvent.click(toggle());
    expect(toggle()).toHaveAttribute("aria-pressed", "true");
    expect(drawn("s1")).toBe(1);
    // Registered without a structure, unregistered, and a reference without a compound.
    expect([drawn("s3"), drawn("s2"), drawn("r1")]).toEqual([0, 0, 0]);
    expect(within(row("s3")).getByRole("link", { name: "CC-000002" })).toBeInTheDocument();
    expect(within(row("s2")).getByTitle("16:0-CoA (unregistered)")).toHaveTextContent(/^16:0-CoA$/);
    expect(within(row("r1")).getByText("MadR")).toBeInTheDocument();

    fireEvent.click(toggle());
    expect(toggle()).toHaveAttribute("aria-pressed", "false");
    expect(screen.queryByTestId("structure")).toBeNull();
  });

  it("draws a pinned reference's structure when the reference is a registered compound", () => {
    const registered = positions.map((p) =>
      p.well_id === "r1" ? { ...p, registration_number: "CC-000009", smiles: "c1ccccc1" } : p,
    );
    render(<Harness at={registered} />);
    fireEvent.click(toggle());
    expect(drawn("r1")).toBe(1);
  });

  it("remembers the choice in this browser", () => {
    const first = render(<Harness />);
    fireEvent.click(toggle());
    expect(localStorage.getItem("cellar.traces.structures")).toBe("1");
    first.unmount();

    const second = render(<Harness />);
    expect(toggle()).toHaveAttribute("aria-pressed", "true");
    expect(drawn("s1")).toBe(1);
    fireEvent.click(toggle());
    expect(localStorage.getItem("cellar.traces.structures")).toBe("0");
    second.unmount();

    render(<Harness />);
    expect(toggle()).toHaveAttribute("aria-pressed", "false");
  });

  it("works for this visit when the browser refuses storage", () => {
    const refuse = () => {
      throw new Error("denied");
    };
    const get = vi.spyOn(localStorage, "getItem").mockImplementation(refuse);
    const set = vi.spyOn(localStorage, "setItem").mockImplementation(refuse);
    render(<Harness />);
    fireEvent.click(toggle());
    expect(drawn("s1")).toBe(1);
    get.mockRestore();
    set.mockRestore();
  });

  it("is off for the shift plot, which draws no structures", () => {
    render(<Harness />);
    fireEvent.mouseDown(screen.getByRole("tab", { name: "Shift plot" }));
    expect(toggle()).toBeDisabled();
  });
});

describe("aliases in the Sample cell", () => {
  /** s1 has one alias; s3 has its compound's name and two synonyms. */
  const withAliases = positions.map((p) =>
    p.well_id === "s1"
      ? { ...p, synonyms: ["SACC-0455096"] }
      : p.well_id === "s3"
        ? { ...p, molecule_name: "Isoniazid", synonyms: ["SACC-0000002", "INH"] }
        : p,
  );
  const sample = (id: string) => (row(id) as HTMLTableRowElement).cells[0];

  it("shows one alias in full, and of several the first with how many more", () => {
    render(<Harness at={withAliases} />);
    const one = within(row("s1")).getByTitle("SACC-0455096");
    expect(one).toHaveTextContent(/^SACC-0455096$/);
    expect(one).toHaveClass("text-muted-foreground");
    // The registration number still links, with its batch suffix.
    expect(sample("s1")).toHaveTextContent(/^CC-014538·001SACC-0455096$/);
    expect(within(row("s1")).getByRole("link", { name: "CC-014538" })).toBeInTheDocument();
    // The tooltip lists every alias.
    const several = within(row("s3")).getByTitle("Isoniazid, SACC-0000002, INH");
    expect(within(several).getByText("Isoniazid")).toBeInTheDocument();
    expect(within(several).getByText("+2")).toBeInTheDocument();
    expect(several).not.toHaveTextContent("INH");
  });

  it("leaves a sample without aliases and an unregistered one as they were", () => {
    render(<Harness at={withAliases.map((p) => (p.well_id === "s1" ? positions[1] : p))} />);
    expect(sample("s1")).toHaveTextContent(/^CC-014538·001$/);
    expect(within(row("s2")).getByTitle("16:0-CoA (unregistered)")).toHaveTextContent(/^16:0-CoA$/);
    expect(sample("s2")).toHaveTextContent(/^16:0-CoA$/);
  });

  it("the search box finds a sample by any of its aliases", () => {
    render(<Harness at={withAliases} />);
    const search = screen.getByPlaceholderText("Find sample, position or batch");
    fireEvent.change(search, { target: { value: "sacc-0455" } });
    expect(bodyIds()).toEqual(["r1", "s1"]);
    // An alias behind "+2" is found too.
    fireEvent.change(search, { target: { value: "INH" } });
    expect(bodyIds()).toEqual(["r1", "s3"]);
  });
});

describe("shift plot toggle", () => {
  it("shows the plot for one window and selects a clicked point", () => {
    const onChange = vi.fn();
    render(<Harness onChange={onChange} />);
    fireEvent.mouseDown(screen.getByRole("tab", { name: "Shift plot" }));
    fireEvent.click(screen.getByRole("tab", { name: "Shift plot" }));
    const p = plots[plots.length - 1];
    expect(p.data[0].customdata).toEqual(["s1", "s3", "s2"]);
    act(() => p.onClick?.({ points: [{ customdata: "s3" }] }));
    expect(onChange.mock.calls[0][0].anchor).toBe("s3");
    expect([...onChange.mock.calls[0][0].selected]).toEqual(["s3"]);
  });

  it("follows the strip's filter", () => {
    render(<Harness />);
    fireEvent.mouseDown(screen.getByRole("tab", { name: "Shift plot" }));
    fireEvent.click(screen.getByRole("button", { name: "1 down" }));
    expect(plots[plots.length - 1].data[0].customdata).toEqual(["s1"]);
  });

  it("is disabled in Compare", () => {
    render(<Harness />);
    fireEvent.mouseDown(screen.getByRole("tab", { name: "Compare" }));
    fireEvent.click(screen.getByRole("tab", { name: "Compare" }));
    expect(screen.getByRole("tab", { name: "Shift plot" })).toBeDisabled();
  });
});

describe("thermal structure inspection", () => {
  beforeEach(() => localStorage.clear());
  afterEach(() => localStorage.clear());
  const withStructures = positions.map((p) => (p.well_id === "s3" ? { ...p, smiles: "CCN" } : p));

  it("shows every available structure in its own column while keeping Position and Compound first", () => {
    const onChange = vi.fn();
    render(
      <Harness at={withStructures} workspace={<div>Trace details</div>} onChange={onChange} />,
    );
    expect(screen.queryByRole("columnheader", { name: "Structure" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Show structures" }));
    expect(screen.getByRole("button", { name: "Hide structures" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    const headers = within(table())
      .getAllByRole("columnheader")
      .map((h) => h.textContent)
      .filter(Boolean);
    expect(headers.slice(0, 3)).toEqual(["Position", "Compound", "Structure"]);
    const resultCells = (row("s1") as HTMLTableRowElement).cells;
    expect(resultCells[headers.indexOf("ΔTm (°C)")]).toHaveTextContent("−8.5");
    expect(resultCells[headers.indexOf("Tm (°C)")]).toHaveTextContent("62.8");
    for (const id of ["s1", "s3"]) {
      const cells = (row(id) as HTMLTableRowElement).cells;
      expect(within(cells[1]).queryByTestId("structure")).toBeNull();
      expect(within(cells[2]).getByTestId("structure")).toBeInTheDocument();
    }
    fireEvent.click(row("s1"));
    fireEvent.click(row("s3"), { metaKey: true });
    expect(lastSelected(onChange)).toEqual(["s1", "s3"]);
    expect(within(table()).getAllByTestId("structure")).toHaveLength(2);
    expect(screen.queryByRole("button", { name: "View structure" })).toBeNull();
    expect(within(row("s2")).getByLabelText("No structure recorded")).toBeInTheDocument();
  });

  it("restores the table structure choice and retains hover previews when structures are hidden", () => {
    localStorage.setItem("cellar.traces.structures", "1");
    render(<Harness at={withStructures} workspace={<div>Trace details</div>} />);
    expect(screen.getByRole("button", { name: "Hide structures" })).toBeInTheDocument();
    expect(within(table()).getAllByTestId("structure")).toHaveLength(2);
    fireEvent.click(screen.getByRole("button", { name: "Hide structures" }));
    expect(screen.queryByRole("columnheader", { name: "Structure" })).toBeNull();
    expect(within(table()).queryByTestId("structure")).toBeNull();
    expect(localStorage.getItem("cellar.traces.structures")).toBe("0");
    act(() => within(row("s1")).getByRole("link", { name: "CC-014538" }).focus());
    expect(screen.getByTestId("structure")).toHaveAttribute("data-smiles", "CCO");
    expect(within(table()).queryByTestId("structure")).toBeNull();
  });
});
