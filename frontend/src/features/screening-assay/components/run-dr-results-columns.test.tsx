import { cleanup, render as renderElement, screen } from "@testing-library/react";
import type { ICellRendererParams } from "ag-grid-community";
import type { ReactElement } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { CurveFrame } from "../lib/curve-frame";
import { DoseResponseSparkline } from "./dose-response-sparkline";
import { buildColumnDefs } from "./run-dr-results-columns";
import type { CompoundCurveRow } from "./run-dr-results-transforms";

vi.mock("./dose-response-sparkline", () => ({ DoseResponseSparkline: vi.fn(() => null) }));
vi.mock("@/shared/components/chemistry", () => ({
  StructureThumbnail: () => null,
  StructureRenderer: () => null,
}));
afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

const row = (y: number) =>
  ({
    molecule_id: `molecule-${y}`,
    registration_number: "CC-123",
    fitted_unit: "uM",
    hill_slope: 1,
    top: 100,
    bottom: 0,
    fitted_value: 1,
    r_squared: 0.9,
    curve_class: "full",
    data_points: [{ x: 1, y }],
    intercept_values: [{ spec: { kind: "ec", level: 50 }, value: null, qualifier: "nd" }],
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
      renderElement(thumbnail);
      expect(DoseResponseSparkline).toHaveBeenLastCalledWith(
        expect.objectContaining({
          xRange: [0.1, 1000],
          yRange: [-10, 110],
          interceptValues: data.intercept_values,
        }),
        undefined,
      );
      // The full class label remains available beside the curve.
      expect(screen.getAllByText("Full").length).toBeGreaterThan(0);
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

describe("run potency display units", () => {
  const spec = { kind: "ec", level: 50, basis: "relative_percent" } as const;
  const column = () => {
    const result = buildColumnDefs([spec], undefined, { unit: "nM" }).find(
      (c) => c.colId === "intercept:ec:50",
    );
    if (!result) throw new Error("Missing intercept column");
    return result;
  };
  it("converts displayed numbers and numeric sorting together without changing the source result", () => {
    const data = {
      ...row(50),
      fitted_value: 0.001745,
      intercept_values: [{ spec, value: 0.001745, qualifier: "=" }],
    } as CompoundCurveRow;
    const col = column();
    expect(col.headerName).toBe("EC50 (nM)");
    expect(
      (col.valueGetter as (params: { data: CompoundCurveRow }) => number | null)({ data }),
    ).toBeCloseTo(1.745);
    renderElement(
      (col.cellRenderer as (params: { data: CompoundCurveRow }) => ReactElement)({ data }),
    );
    expect(screen.getByText("1.745")).toBeInTheDocument();
    expect(data.fitted_value).toBe(0.001745);
  });
  it("preserves censoring and the tested-range explanation when units change", () => {
    const data = {
      ...row(95),
      curve_class: "active_all_doses",
      data_points: [{ x: 0.0002, y: 95 }],
      intercept_values: [{ spec, value: 0.0002, qualifier: "<" }],
    } as CompoundCurveRow;
    const col = column();
    renderElement(
      (col.cellRenderer as (params: { data: CompoundCurveRow }) => ReactElement)({ data }),
    );
    expect(screen.getByText("< 0.2")).toBeInTheDocument();
    expect(screen.getByText("Below tested range")).toBeInTheDocument();
    expect(
      (col.valueGetter as (params: { data: CompoundCurveRow }) => number | null)({ data }),
    ).toBe(Number.NEGATIVE_INFINITY);
  });
  it("keeps ND distinct from a numeric bound", () => {
    renderElement(
      (column().cellRenderer as (params: { data: CompoundCurveRow }) => ReactElement)({
        data: row(50),
      }),
    );
    expect(screen.getByText("ND")).toBeInTheDocument();
    expect(screen.getByText("Not determined")).toBeInTheDocument();
  });
});
