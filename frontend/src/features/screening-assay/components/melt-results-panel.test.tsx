import { act, fireEvent, render, renderHook, screen, within } from "@testing-library/react";
import { useState } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { CurvePosition } from "../lib/curve-plot";
import { EMPTY_SELECTION, type SelectionState } from "../lib/curve-selection";
import { useShiftThreshold } from "../lib/use-shift-threshold";
import type { MeltWindow, MeltingAnalysis, MeltingStep } from "../types";

vi.mock("@/shared/components/chemistry/structure-thumbnail", () => ({
  StructureThumbnail: () => <div data-testid="structure" />,
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

import { MeltResultsPanel } from "./melt-results-panel";

function pos(id: string, over: Record<string, unknown> = {}) {
  return {
    well_id: id,
    position_label: `Capillary ${id}`,
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
const wp = (id: string, tm: number | null, d: number | null, flags: string[] = []) => ({
  well_id: id,
  tm,
  delta_tm: d,
  flags,
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
  ({ well_id: well, channel_key: channel, value, status }) as unknown as MeltingStep;

const analysis = {
  run_id: "run",
  edit_refusal: null,
  windows: [
    win("Main", "a", 50, 85, [
      wp("r1", 71.3, 0),
      wp("s1", 62.8, -8.5),
      wp("s2", 74.3, 3.0),
      wp("s3", 70.3, -1.0),
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
} as unknown as MeltingAnalysis;

function Harness({
  channel = "a",
  onChange = () => {},
  onLead,
  data = analysis,
}: {
  channel?: string;
  onChange?: (s: SelectionState) => void;
  onLead?: (w: string | null) => void;
  data?: MeltingAnalysis;
}) {
  const [selection, setSelection] = useState<SelectionState>(EMPTY_SELECTION);
  return (
    <MeltResultsPanel
      analysis={data}
      positions={positions}
      channel={channel}
      doseUnit="µM"
      selection={selection}
      onSelectionChange={(s) => {
        onChange(s);
        setSelection(s);
      }}
      onLeadWindowChange={onLead}
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
const tabNames = () =>
  within(screen.getByRole("tablist", { name: "Window" }))
    .getAllByRole("tab")
    .map((t) => t.textContent);

beforeEach(() => localStorage.clear());

const lastSelected = (fn: ReturnType<typeof vi.fn>) => [
  ...(fn.mock.lastCall?.[0] as SelectionState).selected,
];

describe("MeltResultsPanel", () => {
  it("lists only the windows of the current signal and keeps the chosen one across a signal change", () => {
    const onLead = vi.fn();
    const { rerender } = render(<Harness channel="a" onLead={onLead} />);
    expect(tabNames()).toEqual(["Main", "Low", "Compare"]);
    expect(onLead).toHaveBeenLastCalledWith("Main");
    fireEvent.mouseDown(screen.getByRole("tab", { name: "Low" }));
    expect(onLead).toHaveBeenLastCalledWith("Low");
    rerender(<Harness channel="b" onLead={onLead} />);
    expect(tabNames()).toEqual(["High", "Low", "Compare"]);
    expect(screen.getByRole("tab", { name: "Low" })).toHaveAttribute("aria-selected", "true");
    // Compare keeps the lead window.
    fireEvent.mouseDown(screen.getByRole("tab", { name: "Compare" }));
    expect(onLead).toHaveBeenLastCalledWith("Low");
  });

  it("lists positions and the no-window sentence when the signal has no window", () => {
    const onLead = vi.fn();
    render(<Harness channel="c" onLead={onLead} />);
    expect(
      screen.getByText(
        "No temperature window on this signal — add one on the protocol's Design tab",
      ),
    ).toBeInTheDocument();
    expect(bodyIds()).toEqual(["r1", "s1", "s2", "s3", "s4"]);
    expect(within(table()).queryByText("Tm (°C)")).not.toBeInTheDocument();
    expect(screen.queryByRole("tablist", { name: "Window" })).not.toBeInTheDocument();
    expect(onLead).toHaveBeenLastCalledWith(null);
  });

  it("shows signed ΔTm in direction colour without a tint, and the status chip", () => {
    render(<Harness />);
    const delta = (id: string, text: string) => within(row(id)).getByText(text).closest("td");
    expect(delta("s1", "−8.5")).toHaveClass("text-red-700", "font-semibold");
    expect(delta("s2", "+3.0")).toHaveClass("text-blue-700", "font-semibold");
    expect(delta("s2", "+3.0")?.className).not.toMatch(/bg-/);
    expect(delta("s3", "−1.0")).toHaveClass("text-muted-foreground");
    expect(within(row("s3")).getByText("Provisional")).toBeInTheDocument();
    expect(within(row("s1")).getByText("Reviewed")).toBeInTheDocument();
    expect(within(row("s4")).getByText("No step")).toBeInTheDocument();
    // The reference's own counting step in the shown window is accepted.
    expect(within(row("r1")).getByText("Reference · Reviewed")).toBeInTheDocument();
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
    expect(screen.getByRole("button", { name: "Provisional 1" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "1 up" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "1 down" })).toBeInTheDocument();
    const needs = screen.getByRole("button", { name: "Step issues 1" });
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
    render(<Harness />);
    fireEvent.mouseDown(screen.getByRole("tab", { name: "Compare" }));
    const t = within(table());
    expect(t.getByRole("columnheader", { name: "Main" })).toBeInTheDocument();
    expect(t.getByRole("columnheader", { name: "Low" })).toBeInTheDocument();
    expect(t.getAllByRole("columnheader", { name: "Tm (°C)" })).toHaveLength(2);
    expect(t.getAllByRole("columnheader", { name: "ΔTm (°C)" })).toHaveLength(2);
    expect(bodyIds()).toEqual(["r1", "s3", "s1", "s2", "s4"]);
    // Worst status across windows: provisional in Main beats reviewed in Low.
    expect(within(row("s3")).getByText("Provisional")).toBeInTheDocument();
    expect(within(row("s3")).getByText("−10.0").closest("td")).toHaveClass("text-red-700");
    // The strip names what it counts and gives each window's reference.
    expect(screen.getByText("All windows", { selector: "span" })).toBeInTheDocument();
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

  it("ΔTm is judged as shown: +1.96 at a threshold of 2 reads +2.0 and counts up", () => {
    const data = {
      ...analysis,
      windows: analysis.windows.map((w, i) =>
        i === 0
          ? {
              ...w,
              positions: w.positions.map((p) => (p.well_id === "s3" ? wp("s3", 73, 1.96) : p)),
            }
          : w,
      ),
    } as MeltingAnalysis;
    render(<Harness data={data} />);
    expect(within(row("s3")).getByText("+2.0").closest("td")).toHaveClass("text-blue-700");
    expect(screen.getByRole("button", { name: "2 up" })).toBeInTheDocument();
  });

  it("an unreviewed reference is a button that selects it, and its chip says Provisional", () => {
    const onChange = vi.fn();
    const data = {
      ...analysis,
      steps: analysis.steps.map((s) => (s.well_id === "r1" ? step("r1", 71.3, "unreviewed") : s)),
    } as MeltingAnalysis;
    render(<Harness data={data} onChange={onChange} />);
    expect(within(row("r1")).getByText("Reference · Provisional")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Reference not reviewed" }));
    expect(lastSelected(onChange)).toEqual(["r1"]);
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

  it("focusing a registration number shows the structure", () => {
    render(<Harness />);
    expect(screen.queryByTestId("structure")).toBeNull();
    act(() => within(row("s1")).getByRole("link", { name: "CC-014538" }).focus());
    expect(screen.getAllByTestId("structure").length).toBeGreaterThan(0);
  });
});

describe("useShiftThreshold", () => {
  it("threshold is read from and saved to localStorage, falling back to 2", () => {
    const key = "cellar.thermalShift.threshold";
    expect(renderHook(() => useShiftThreshold()).result.current[0]).toBe(2);
    localStorage.setItem(key, "3");
    const { result } = renderHook(() => useShiftThreshold());
    expect(result.current[0]).toBe(3);
    act(() => result.current[1](1.5));
    expect(result.current[0]).toBe(1.5);
    expect(localStorage.getItem(key)).toBe("1.5");
    act(() => result.current[1](0));
    expect(result.current[0]).toBe(2);
    act(() => result.current[1](Number.NaN));
    expect(result.current[0]).toBe(2);
    localStorage.setItem(key, "-1");
    expect(renderHook(() => useShiftThreshold()).result.current[0]).toBe(2);
    const spy = vi.spyOn(localStorage, "getItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    expect(renderHook(() => useShiftThreshold()).result.current[0]).toBe(2);
    spy.mockRestore();
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
