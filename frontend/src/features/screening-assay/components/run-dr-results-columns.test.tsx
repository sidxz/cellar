import type { ICellRendererParams } from "ag-grid-community";
import type { ReactElement } from "react";
import { describe, expect, it } from "vitest";
import type { CurveFrame } from "../lib/curve-frame";
import { buildColumnDefs } from "./run-dr-results-columns";
import type { CompoundCurveRow } from "./run-dr-results-transforms";

const row = (y: number) =>
  ({
    hill_slope: 1,
    top: 100,
    bottom: 0,
    fitted_value: 1,
    r_squared: 0.9,
    curve_class: "full",
    data_points: [{ x: 1, y }],
  }) as unknown as CompoundCurveRow;

describe("run dose-response curve column", () => {
  it("hands every row's thumbnail the table's one frame", () => {
    const frame: CurveFrame = { xRange: [0.1, 1000], yRange: [-10, 110] };
    const curve = buildColumnDefs([], frame).find((c) => c.colId === "sparkline");
    const render = curve?.cellRenderer as (
      p: ICellRendererParams<CompoundCurveRow>,
    ) => ReactElement;

    for (const data of [row(20), row(95)]) {
      const thumbnail = render({ data } as ICellRendererParams<CompoundCurveRow>);
      expect(thumbnail.props).toMatchObject({ xRange: [0.1, 1000], yRange: [-10, 110] });
    }
  });
});

describe("run dose-response intercept column", () => {
  it("sorts a value stored as below the lowest dose ahead of every exact value", () => {
    const spec = { kind: "ec", level: 50, basis: "relative_percent" } as const;
    const col = buildColumnDefs([spec]).find((c) => c.headerName?.startsWith("EC50"));
    const getter = col?.valueGetter as (p: { data: CompoundCurveRow }) => unknown;
    const data = {
      ...row(95),
      data_points: [
        { x: 0.0002, y: 92 },
        { x: 100, y: 95 },
      ],
      intercept_values: [{ spec, value: 0.0002, at_bound: false, qualifier: "<" }],
    } as unknown as CompoundCurveRow;
    expect(getter({ data })).toBe(Number.NEGATIVE_INFINITY);
  });
});
