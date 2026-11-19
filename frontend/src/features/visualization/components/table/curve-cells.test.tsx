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

import type { Dataset } from "../../types";
import { CurveSparklineCell } from "./curve-cells";

/** One Runs row of a partial curve whose EC50 the fit puts at `value` / `q`. */
const run = (value: number | null, q: string | null): Dataset =>
  ({
    revision: "r",
    level: "runs",
    row_count: 1,
    row_ids: ["r1"],
    columns: [],
    values: {
      "dr:e": [value],
      "dr:e:q": [q],
      "dr:e:midpoint": [1],
      "dr:e:top": [100],
      "dr:e:bottom": [0],
      "dr:e:hill_slope": [1],
      "dr:e:curve_class": ["partial"],
      "dr:e:points": [
        [
          { x: 0.01, y: 5 },
          { x: 100, y: 55 },
        ],
      ],
    },
  }) as unknown as Dataset;

function lines(ds: Dataset) {
  plotCalls.length = 0;
  render(<CurveSparklineCell ds={ds} valueKey="dr:e" i={0} compact={false} onOpen={() => {}} />);
  return (plotCalls.at(-1)?.layout.shapes ?? []).map((s) => s.x0);
}

describe("<CurveSparklineCell /> intercept line", () => {
  it("draws no line at a censored or n.d. headline, and one at an exact one", () => {
    expect(lines(run(100, ">"))).toEqual([]);
    expect(lines(run(null, null))).toEqual([]);
    expect(lines(run(0.8, null))).toEqual([1]);
  });
});
