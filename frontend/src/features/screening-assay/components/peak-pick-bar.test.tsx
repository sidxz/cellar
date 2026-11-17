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
  it("a picked peak shows its facts, the windows to name it, and Accept, Reject, Move", () => {
    const on = show();
    expect(screen.getByRole("region", { name: "Peak picked" })).toHaveTextContent(
      "Capillary 7 · peak at 48.1 °C · Instrument · Unreviewed",
    );
    expect(buttons()).toEqual([
      "Clear the pick",
      "Main 50–85 °C",
      "Low 25–50 °C",
      "by temperature",
      "Accept",
      "Reject",
      "Move",
    ]);
    // Unassigned, the peak is named by its temperature.
    expect(screen.getByRole("button", { name: "by temperature" })).toHaveAttribute(
      "aria-current",
      "true",
    );
    expect(screen.getByRole("button", { name: "Main 50–85 °C" })).not.toHaveAttribute(
      "aria-current",
    );
    press("Main 50–85 °C");
    expect(on.onAssign).toHaveBeenLastCalledWith("Main");
    press("by temperature");
    expect(on.onAssign).toHaveBeenLastCalledWith(null);
    for (const [name, fn] of [
      ["Accept", on.onAccept],
      ["Reject", on.onReject],
      ["Move", on.onMove],
      ["Clear the pick", on.onClear],
    ] as const) {
      press(name);
      expect(fn).toHaveBeenCalledTimes(1);
    }
    expect(on.onAdd).not.toHaveBeenCalled();
  });

  it("says which window an assigned peak has, and offers no Accept once accepted", () => {
    show({ step: { ...PEAK, status: "accepted", assigned_window: "Main" } });
    expect(screen.getByRole("region", { name: "Peak picked" })).toHaveTextContent(
      "Capillary 7 · peak at 48.1 °C · Instrument · Accepted · assigned to Main",
    );
    expect(screen.getByRole("button", { name: "Main 50–85 °C" })).toHaveAttribute(
      "aria-current",
      "true",
    );
    expect(screen.getByRole("button", { name: "by temperature" })).not.toHaveAttribute(
      "aria-current",
    );
    expect(screen.queryByRole("button", { name: "Accept" })).toBeNull();
  });

  it("an assignment to a name that is no window on the signal counts as none", () => {
    show({ step: { ...PEAK, assigned_window: "Gone" } });
    expect(screen.getByRole("region", { name: "Peak picked" })).not.toHaveTextContent("assigned");
    expect(screen.getByRole("button", { name: "by temperature" })).toHaveAttribute(
      "aria-current",
      "true",
    );
  });

  it("while moving, says to click the new temperature", () => {
    show({ moving: true });
    expect(
      screen.getByText("Click the new temperature on this position's trace."),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Move" })).toHaveAttribute("aria-pressed", "true");
  });

  it("a picked spot offers to add a peak there, with the window choices", () => {
    const on = show(SPOT);
    expect(screen.getByRole("region", { name: "Spot picked" })).toHaveTextContent(
      "Capillary 7 · 52.3 °C",
    );
    expect(buttons()).toEqual([
      "Clear the pick",
      "Add a peak here",
      "Main 50–85 °C",
      "Low 25–50 °C",
      "not yet",
    ]);
    press("Add a peak here");
    expect(on.onAdd).toHaveBeenLastCalledWith(null);
    press("Low 25–50 °C");
    expect(on.onAdd).toHaveBeenLastCalledWith("Low");
    press("not yet");
    expect(on.onAdd).toHaveBeenLastCalledWith(null);
    expect(on.onAssign).not.toHaveBeenCalled();
  });

  it("without windows on the signal, offers only the actions that need none", () => {
    show({ windows: [] });
    expect(buttons()).toEqual(["Clear the pick", "Accept", "Reject", "Move"]);
  });

  it.each([
    ["Peak picked", {}, "Capillary 7 · peak at 48.1 °C · Instrument · Unreviewed"],
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
