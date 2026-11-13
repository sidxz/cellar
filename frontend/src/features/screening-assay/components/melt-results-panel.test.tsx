import { act, fireEvent, render, renderHook, screen, within } from "@testing-library/react";
import { type ReactNode, useState } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { CurvePosition } from "../lib/curve-plot";
import { EMPTY_SELECTION, type SelectionState } from "../lib/curve-selection";
import { useShiftThreshold } from "../lib/use-shift-threshold";
import type { MeltWindow, MeltingAnalysis, MeltingStep } from "../types";

vi.mock("@/shared/components/chemistry/structure-thumbnail", () => ({
  StructureThumbnail: () => <div data-testid="structure" />,
}));

interface MockCol {
  headerName?: string;
  hide?: boolean;
  children?: MockCol[];
  valueGetter?: (p: { data: unknown }) => unknown;
  valueFormatter?: (p: { data: unknown; value: unknown }) => string;
  cellRenderer?: (p: { data: unknown; value: unknown }) => ReactNode;
  cellClass?: string | ((p: { data: unknown; value: unknown }) => string | undefined);
}
interface MockGridProps {
  rowData: unknown[];
  pinnedTopRowData?: unknown[];
  columnDefs: MockCol[];
  getRowId: (p: { data: unknown }) => string;
  rowClassRules?: Record<string, (p: { data: unknown }) => boolean>;
  onRowClicked?: (e: { data: unknown; event: MouseEvent; api: unknown }) => void;
}
// The grid as a plain table: pinned rows then body rows, through the column
// renderers, and row clicks reach onRowClicked with the native event.
vi.mock("@/shared/components/data-grid/data-grid", () => ({
  DataGrid: (props: MockGridProps) => {
    const leaves = props.columnDefs.flatMap((c) => c.children ?? [c]).filter((c) => !c.hide);
    const api = {
      forEachNodeAfterFilterAndSort: (cb: (n: { data: unknown }) => void) => {
        for (const data of props.rowData) cb({ data });
      },
    };
    return (
      <table>
        <thead>
          <tr>
            {props.columnDefs.map((c, i) => (
              <th key={i}>{c.children ? c.headerName : ""}</th>
            ))}
          </tr>
          <tr>
            {leaves.map((c, i) => (
              <th key={i}>{c.headerName}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {[...(props.pinnedTopRowData ?? []), ...props.rowData].map((data) => {
            const id = props.getRowId({ data });
            return (
              <tr
                key={id}
                data-row-id={id}
                className={Object.entries(props.rowClassRules ?? {})
                  .filter(([, rule]) => rule({ data }))
                  .map(([cls]) => cls)
                  .join(" ")}
                onClick={(e) => props.onRowClicked?.({ data, event: e.nativeEvent, api })}
              >
                {leaves.map((c, i) => {
                  const p = { data, value: c.valueGetter?.({ data }) };
                  const cls = typeof c.cellClass === "function" ? c.cellClass(p) : c.cellClass;
                  return (
                    <td key={i} className={cls}>
                      {c.cellRenderer
                        ? c.cellRenderer(p)
                        : c.valueFormatter
                          ? c.valueFormatter(p)
                          : String(p.value ?? "")}
                    </td>
                  );
                })}
              </tr>
            );
          })}
        </tbody>
      </table>
    );
  },
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
}: {
  channel?: string;
  onChange?: (s: SelectionState) => void;
  onLead?: (w: string | null) => void;
}) {
  const [selection, setSelection] = useState<SelectionState>(EMPTY_SELECTION);
  return (
    <MeltResultsPanel
      analysis={analysis}
      positions={positions}
      channel={channel}
      doseUnit="µM"
      selection={selection}
      onSelectionChange={(s) => {
        onChange(s);
        setSelection(s);
      }}
      showReferences
      onShowReferencesChange={() => {}}
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

  it("shows signed ΔTm with direction tint and the status chip", () => {
    render(<Harness />);
    const delta = (id: string, text: string) => within(row(id)).getByText(text).closest("td");
    expect(delta("s1", "−8.5")).toHaveClass("text-red-700");
    expect(delta("s2", "+3.0")).toHaveClass("text-blue-700");
    expect(delta("s3", "−1.0")).toHaveClass("text-muted-foreground");
    expect(within(row("s3")).getByText("Provisional")).toBeInTheDocument();
    expect(within(row("s1")).getByText("Reviewed")).toBeInTheDocument();
    expect(within(row("s4")).getByText("No step")).toBeInTheDocument();
    expect(within(row("r1")).getByText("Reference")).toBeInTheDocument();
    expect(within(row("r1")).getByText("—")).toBeInTheDocument();
    // Identity: registered links to the compound with the batch suffix; unregistered is muted.
    expect(within(row("s1")).getByRole("link", { name: "CC-014538" })).toHaveAttribute(
      "href",
      "/compounds/m1",
    );
    expect(within(row("s1")).getByText("·001")).toBeInTheDocument();
    expect(within(row("s2")).getByText("unregistered")).toBeInTheDocument();
    // Samples by |ΔTm|, missing last; references pinned first.
    expect(bodyIds()).toEqual(["r1", "s1", "s2", "s3", "s4"]);
  });

  it("strip counts filter the grid and a second click clears", () => {
    render(<Harness />);
    expect(screen.getByText("Reference MadR 71.3 °C (n=1)")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Provisional 1" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "1 up" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "1 down" })).toBeInTheDocument();
    const needs = screen.getByRole("button", { name: "Needs review 1" });
    fireEvent.click(needs);
    expect(needs).toHaveAttribute("aria-pressed", "true");
    expect(bodyIds()).toEqual(["r1", "s4"]);
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
