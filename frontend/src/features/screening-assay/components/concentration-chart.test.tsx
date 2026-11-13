import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

type P = {
  data: Record<string, any>[];
  layout: Record<string, any>;
  config: Record<string, unknown>;
  onClick?: (e: unknown) => void;
};
const plots: P[] = [];
vi.mock("@/shared/lib/plotly", () => ({
  Plot: (p: P) => {
    plots.push(p);
    return (
      <button
        type="button"
        data-testid="plot"
        onClick={() => p.onClick?.({ points: [{ customdata: "b" }] })}
      />
    );
  },
}));

import { selectedOutline } from "../lib/shift-figure";
import { ConcentrationChart } from "./concentration-chart";

const points = [
  { wellId: "a", dose: 1, deltaTm: 0.5, provisional: false },
  { wellId: "b", dose: 10, deltaTm: 3, provisional: true },
  { wellId: "c", dose: 10, deltaTm: 5, provisional: false },
  { wellId: "d", dose: 100, deltaTm: 6, provisional: false },
];
const last = () => plots[plots.length - 1];
const show = (selected: string[] = [], onSelect = () => {}) =>
  render(
    <ConcentrationChart
      title="CC-1 · 001 — ΔTm (Main) by concentration"
      points={points}
      doseUnit="µM"
      threshold={2}
      selected={new Set(selected)}
      onSelect={onSelect}
    />,
  );

beforeEach(() => {
  plots.length = 0;
});

describe("ConcentrationChart", () => {
  it("plots the anchor's batch with ticks at measured doses", () => {
    show(["c"]);
    expect(screen.getByText("CC-1 · 001 — ΔTm (Main) by concentration")).toBeTruthy();
    const pts = last().data[0];
    expect(pts.x).toEqual([1, 10, 10, 100]);
    expect(pts.y).toEqual([0.5, 3, 5, 6]);
    expect(pts.marker.size).toEqual([8, 8, 11, 8]);
    expect(last().layout.xaxis).toMatchObject({
      type: "log",
      tickvals: [1, 10, 100],
      ticktext: ["1", "10", "100"],
    });
    expect(last().layout.xaxis.title.text).toContain("µM");
    expect(last().layout.yaxis.title.text).toBe("ΔTm (°C)");
    expect(last().layout.height).toBe(260);
    expect(last().config).toEqual({ displayModeBar: false, responsive: true });
    expect(last().layout.shapes[0]).toMatchObject({ y0: -2, y1: 2 });
    // Labels at the left end, the band's below it and the zero line's above;
    // nothing at the right edge, where the highest dose sits.
    expect(last().layout.annotations).toMatchObject([
      { text: "within ±2 °C", x: 0, xanchor: "left", y: -2, yanchor: "top" },
      { text: "ΔTm = 0 (reference)", x: 0, xanchor: "left", y: 0, yanchor: "bottom" },
    ]);
    expect(pts.marker.line.color).toBe(selectedOutline(undefined));
  });

  it("draws provisional points hollow and says so on hover", () => {
    show();
    const pts = last().data[0];
    expect(pts.marker.symbol).toEqual(["circle", "circle-open", "circle", "circle"]);
    expect(pts.marker.line.width).toEqual([0, 2, 0, 0]);
    expect(pts.text).toEqual(["Reviewed", "Provisional", "Reviewed", "Reviewed"]);
    expect(pts.hovertemplate).toContain("%{text}");
  });

  it("joins means in dose order with a tick where a dose repeats", () => {
    show();
    const line = last().data[1];
    expect(line.x).toEqual([1, 10, 100]);
    expect(line.y).toEqual([0.5, 4, 6]);
    expect(line.mode).toBe("lines");
    const ticks = last().data[2];
    expect(ticks.x).toEqual([10]);
    expect(ticks.y).toEqual([4]);
  });

  it("click selects", () => {
    const onSelect = vi.fn();
    show([], onSelect);
    fireEvent.click(screen.getByTestId("plot"));
    expect(onSelect).toHaveBeenCalledWith("b");
  });
});
