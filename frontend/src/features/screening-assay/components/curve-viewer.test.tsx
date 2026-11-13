import { fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { type CurveSet, curveSetFromRun } from "../lib/curve-plot";
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
  return (
    <CurveViewer
      set={set}
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

beforeEach(() => {
  plotCalls.length = 0;
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
});
