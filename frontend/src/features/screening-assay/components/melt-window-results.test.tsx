import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { CurvePosition } from "../lib/curve-plot";
import type { MeltWindow, StepCheck } from "../types";

const plots: { data: Record<string, unknown>[]; layout: Record<string, unknown> }[] = [];
vi.mock("@/shared/lib/plotly", () => ({
  Plot: (p: (typeof plots)[number]) => {
    plots.push(p);
    return <div data-testid="plot" />;
  },
}));
vi.mock("@/shared/components/data-grid/data-grid", () => ({
  DataGrid: ({ rowData }: { rowData: unknown[] }) => <div data-testid="grid">{rowData.length}</div>,
}));

import { MeltWindowResults } from "./melt-window-results";

function pos(id: string, dose: number | null, batch = "B-1") {
  return {
    well_id: id,
    position_label: id,
    label: null,
    well_type: "sample",
    batch_number: batch,
    dose,
  } as unknown as CurvePosition;
}

function win(over: Partial<MeltWindow> = {}): MeltWindow {
  return {
    window: "Main",
    channel_key: "a",
    low: 50,
    high: 85,
    tm_readout_id: "t",
    delta_tm_readout_id: "d",
    reference_tm: 71.3,
    reference_count: 2,
    flags: [],
    positions: [
      { well_id: "x", tm: 64, delta_tm: -7.3, flags: [] },
      { well_id: "y", tm: 66, delta_tm: -5.3, flags: [] },
    ],
    ...over,
  } as MeltWindow;
}

const noChecks: StepCheck[] = [];
const render1 = (w: MeltWindow, positions: CurvePosition[], checks = noChecks) =>
  render(<MeltWindowResults windows={[w]} positions={positions} checks={checks} doseUnit="µM" />);

describe("MeltWindowResults", () => {
  it("shows the reference line or the no-reference sentence", () => {
    plots.length = 0;
    const { unmount } = render1(win(), [pos("x", 1), pos("y", 10)]);
    expect(screen.getByText("Main (50–85 °C)")).toBeTruthy();
    expect(screen.getByText("Reference Tm 71.3 °C from 2 positions")).toBeTruthy();
    expect(screen.getByTestId("plot")).toBeTruthy();
    const layout = plots[0].layout as { xaxis: { type: string; title: { text: string } } };
    expect(layout.xaxis.type).toBe("log");
    expect(layout.xaxis.title.text).toContain("µM");
    unmount();
    render1(win({ reference_tm: null, reference_count: 0 }), [pos("x", 1), pos("y", 10)]);
    expect(screen.getByText("No reference value in this window")).toBeTruthy();
  });

  it("ticks the concentration axis at the measured concentrations", () => {
    plots.length = 0;
    render1(win(), [pos("x", 25), pos("y", 6.25)]);
    const { xaxis } = plots[0].layout as { xaxis: { tickvals: number[]; ticktext: string[] } };
    expect(xaxis.tickvals).toEqual([6.25, 25]);
    expect(xaxis.ticktext).toEqual(["6.25", "25"]);
  });

  it("draws no plot when no batch has two concentrations", () => {
    render1(win(), [pos("x", 1), pos("y", 1)]);
    expect(screen.queryByTestId("plot")).toBeNull();
    expect(screen.getByTestId("grid").textContent).toBe("2");
  });

  it("says when references differ in their number of steps", () => {
    render1(win(), [pos("x", 1)], [{ channel_key: "a", differs: [], references_differ: true }]);
    expect(screen.getByText("References differ in their number of steps")).toBeTruthy();
  });
});
