import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { MeltingStep } from "../types";
import { PeakPickBar } from "./peak-pick-bar";

const position = {
  well_id: "w7",
  position: "A7",
  row: "A",
  column: 7,
  well_type: "sample",
  registration_number: null,
  position_label: "Capillary 7",
  label: "ABC-0000007",
  note: null,
};
const WINDOWS = [
  { window: "Main", low: 50, high: 85 },
  { window: "Low", low: 25, high: 50 },
];
const PEAK: MeltingStep = {
  id: "p2",
  well_id: "w7",
  channel_key: "a",
  source: "instrument",
  value: 48.1,
  instrument_value: 48.1,
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
};

function show(over: Partial<Parameters<typeof PeakPickBar>[0]> = {}) {
  const on = {
    onAssign: vi.fn(),
    onAccept: vi.fn(),
    onReject: vi.fn(),
    onMove: vi.fn(),
    onAdd: vi.fn(),
    onClear: vi.fn(),
  };
  render(
    <PeakPickBar
      pick={{ wellId: "w7", x: 48.4, stepId: "p2" }}
      position={position}
      step={PEAK}
      windows={WINDOWS}
      useAsTm
      unit="°C"
      refusal={null}
      moving={false}
      {...on}
      {...over}
    />,
  );
  return on;
}

const SPOT = { pick: { wellId: "w7", x: 52.3046, stepId: null }, step: null };
const buttons = () =>
  screen.getAllByRole("button").map((b) => b.getAttribute("aria-label") ?? b.textContent);
const press = (name: string) => fireEvent.click(screen.getByRole("button", { name }));

describe("PeakPickBar", () => {
  it("a picked peak shows its facts, Use as Tm per transition, and Mark reviewed, Exclude, Move", () => {
    const on = show();
    // An unreviewed peak has no status word: the facts end on where it came from.
    expect(screen.getByText("Capillary 7 · peak at 48.1 °C · From instrument")).toBeInTheDocument();
    // No transition was set by hand, so there is none to give back to the temperature range.
    expect(buttons()).toEqual([
      "Clear the pick",
      "Use as Tm (Main)",
      "Use as Tm (Low)",
      "Mark reviewed",
      "Exclude",
      "Move",
    ]);
    expect(screen.getByRole("button", { name: "Use as Tm (Main)" })).not.toHaveAttribute(
      "aria-current",
    );
    press("Use as Tm (Main)");
    expect(on.onAssign).toHaveBeenLastCalledWith("Main");
    for (const [name, fn] of [
      ["Mark reviewed", on.onAccept],
      ["Exclude", on.onReject],
      ["Move", on.onMove],
      ["Clear the pick", on.onClear],
    ] as const) {
      press(name);
      expect(fn).toHaveBeenCalledTimes(1);
    }
    expect(on.onAdd).not.toHaveBeenCalled();
  });

  it("says which transition a peak set by hand has, offers to undo it, and no Mark reviewed once reviewed", () => {
    const on = show({ step: { ...PEAK, status: "accepted", assigned_window: "Main" } });
    expect(screen.getByRole("region", { name: "Peak picked" })).toHaveTextContent(
      "Capillary 7 · peak at 48.1 °C · From instrument · Reviewed · used as Tm (Main)",
    );
    expect(screen.getByRole("button", { name: "Use as Tm (Main)" })).toHaveAttribute(
      "aria-current",
      "true",
    );
    press("By temperature range");
    expect(on.onAssign).toHaveBeenLastCalledWith(null);
    expect(screen.queryByRole("button", { name: "Mark reviewed" })).toBeNull();
  });

  it("a transition set by hand under a name that is none on the signal counts as none", () => {
    show({ step: { ...PEAK, assigned_window: "Gone" } });
    expect(screen.getByRole("region", { name: "Peak picked" })).not.toHaveTextContent("used as Tm");
    expect(screen.queryByRole("button", { name: "By temperature range" })).toBeNull();
  });

  it("with one transition on the signal, the choices do not name it", () => {
    const on = show({ windows: [WINDOWS[0]] });
    press("Use as Tm");
    expect(on.onAssign).toHaveBeenLastCalledWith("Main");
  });

  it("where using the peak as Tm would change nothing, it is not offered", () => {
    show({ windows: [WINDOWS[0]], useAsTm: false });
    expect(buttons()).toEqual(["Clear the pick", "Mark reviewed", "Exclude", "Move"]);
  });

  it("while moving, shows Move pressed", () => {
    show({ moving: true });
    expect(screen.getByRole("button", { name: "Move" })).toHaveAttribute("aria-pressed", "true");
  });

  it("a picked spot offers to add a peak there, and to add it as a transition's Tm", () => {
    const on = show(SPOT);
    expect(screen.getByRole("region", { name: "Spot picked" })).toHaveTextContent(
      "Capillary 7 · 52.3 °C",
    );
    expect(buttons()).toEqual([
      "Clear the pick",
      "Add a peak here",
      "Add and use as Tm (Main)",
      "Add and use as Tm (Low)",
    ]);
    press("Add a peak here");
    expect(on.onAdd).toHaveBeenLastCalledWith(null);
    press("Add and use as Tm (Low)");
    expect(on.onAdd).toHaveBeenLastCalledWith("Low");
    expect(on.onAssign).not.toHaveBeenCalled();
  });

  it("a picked spot on a signal with one transition does not name it", () => {
    const on = show({ ...SPOT, windows: [WINDOWS[0]] });
    press("Add and use as Tm");
    expect(on.onAdd).toHaveBeenLastCalledWith("Main");
  });

  it("a picked spot where the added peak could only be that Tm offers only to add it", () => {
    show({ ...SPOT, windows: [WINDOWS[0]], useAsTm: false });
    expect(buttons()).toEqual(["Clear the pick", "Add a peak here"]);
  });

  it("without transitions on the signal, offers only the actions that need none", () => {
    show({ windows: [], useAsTm: false });
    expect(buttons()).toEqual(["Clear the pick", "Mark reviewed", "Exclude", "Move"]);
  });

  it.each([
    ["Peak picked", {}, "Capillary 7 · peak at 48.1 °C · From instrument"],
    ["Spot picked", SPOT, "Capillary 7 · 52.3 °C"],
  ])("with a refusal, %s shows the facts and the refusal and no buttons", (name, over, facts) => {
    const refusal = "Peaks cannot be changed on an approved run";
    show({ ...over, refusal });
    const bar = screen.getByRole("region", { name });
    expect(bar).toHaveTextContent(facts);
    expect(bar).toHaveTextContent(refusal);
    expect(screen.queryAllByRole("button")).toHaveLength(0);
  });
});
