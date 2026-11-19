import { render } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

// Capture what the shared renderer hands Plotly: the marks drawn, not the props.
const plotCalls: Array<{ layout: { shapes?: Array<{ x0: number }> } }> = [];
vi.mock("@/shared/lib/plotly", () => ({
  Plot: (props: (typeof plotCalls)[number]) => {
    plotCalls.push(props);
    return null;
  },
}));

import { DoseResponseSparkline } from "./dose-response-sparkline";

const PARAMS = { fitted_value: 1, top: 100, bottom: 0, hill_slope: 1, r_squared: 0.9 };
const POINTS = [
  { x: 0.01, y: 5 },
  { x: 1, y: 40 },
  { x: 100, y: 55 },
];
const headline = (qualifier: string) => [
  {
    spec: { kind: "ec", level: 50 },
    value: qualifier === "nd" ? null : 100,
    at_bound: qualifier === ">",
    qualifier,
  },
];

/** The x of every line drawn on the last thumbnail. */
function lines(interceptValues?: ReturnType<typeof headline>) {
  plotCalls.length = 0;
  render(
    <DoseResponseSparkline
      params={PARAMS}
      dataPoints={POINTS}
      curveClass="partial"
      interceptValues={interceptValues}
    />,
  );
  return (plotCalls.at(-1)?.layout.shapes ?? []).map((s) => s.x0);
}

describe("<DoseResponseSparkline /> intercept line", () => {
  it("draws no line at a headline that is censored or n.d.", () => {
    // A 40–60 % partial curve: its midpoint (1) is not where EC50 lies.
    expect(lines(headline("nd"))).toEqual([]);
    expect(lines(headline(">"))).toEqual([]);
    expect(lines(headline("<"))).toEqual([]);
  });

  it("keeps the line at an exact headline, and on a curve fitted before qualifiers", () => {
    expect(lines(headline("="))).toEqual([1]);
    expect(lines()).toEqual([1]);
  });
});
