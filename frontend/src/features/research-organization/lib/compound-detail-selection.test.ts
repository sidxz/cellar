import { describe, expect, it } from "vitest";
import { aggregateValue, pickRepresentative } from "./compound-detail-selection";
import type { CurveDetail } from "../types";

function makeCurve(over: Partial<CurveDetail>): CurveDetail {
  return {
    curve_id: "c1",
    run_id: "r1",
    run_date: null,
    batch_id: "b1",
    readout_definition_id: "rd1",
    curve_type: "ic50",
    fitted_value: 1,
    fitted_unit: "uM",
    hill_slope: -1,
    r_squared: 0.9,
    curve_class: "full",
    top: 100,
    bottom: 0,
    num_points: 8,
    confidence_interval_low: null,
    confidence_interval_high: null,
    raw_data: [],
    excluded_points: null,
    fit_quality_warnings: [],
    intercept_values: [],
    ...over,
  };
}

describe("pickRepresentative", () => {
  it("returns null on empty input", () => {
    expect(pickRepresentative([], "latest")).toBeNull();
    expect(pickRepresentative([], "best_r2")).toBeNull();
  });

  it("best_r2 picks highest r_squared regardless of date", () => {
    const a = makeCurve({ curve_id: "a", r_squared: 0.9, run_date: "2026-05-01" });
    const b = makeCurve({ curve_id: "b", r_squared: 0.99, run_date: "2026-01-01" });
    expect(pickRepresentative([a, b], "best_r2")!.curve_id).toBe("b");
  });

  it("latest picks newest run_date regardless of R²", () => {
    const a = makeCurve({ curve_id: "a", r_squared: 0.99, run_date: "2026-01-01" });
    const b = makeCurve({ curve_id: "b", r_squared: 0.85, run_date: "2026-05-01" });
    expect(pickRepresentative([a, b], "latest")!.curve_id).toBe("b");
  });

  it("gmean and mean also pick newest run_date (rep = chart shape anchor)", () => {
    const a = makeCurve({ curve_id: "a", run_date: "2026-01-01" });
    const b = makeCurve({ curve_id: "b", run_date: "2026-05-01" });
    expect(pickRepresentative([a, b], "gmean")!.curve_id).toBe("b");
    expect(pickRepresentative([a, b], "mean")!.curve_id).toBe("b");
  });

  it("null run_date sorts to the back for latest mode", () => {
    // A populated date always beats a missing one — keeps the rep from
    // landing on a curve whose owning Run was deleted out-of-band.
    const dated = makeCurve({ curve_id: "dated", run_date: "2026-01-01" });
    const undated = makeCurve({ curve_id: "undated", run_date: null });
    expect(pickRepresentative([undated, dated], "latest")!.curve_id).toBe("dated");
  });
});

describe("aggregateValue", () => {
  it("returns null when every contributor is inactive", () => {
    const xs = [
      makeCurve({ fitted_value: 0.1, curve_class: "inactive" }),
      makeCurve({ fitted_value: 0.2, curve_class: "inactive" }),
    ];
    expect(aggregateValue(xs, "gmean")).toBeNull();
    expect(aggregateValue(xs, "mean")).toBeNull();
  });

  it("gmean of (0.10, 0.40) = 0.20", () => {
    // gmean = (0.1 * 0.4)^0.5 = sqrt(0.04) = 0.2
    const xs = [
      makeCurve({ fitted_value: 0.1 }),
      makeCurve({ fitted_value: 0.4 }),
    ];
    expect(aggregateValue(xs, "gmean")).toBeCloseTo(0.2, 3);
  });

  it("mean of (10, 20, 30) = 20", () => {
    const xs = [
      makeCurve({ fitted_value: 10 }),
      makeCurve({ fitted_value: 20 }),
      makeCurve({ fitted_value: 30 }),
    ];
    expect(aggregateValue(xs, "mean")).toBeCloseTo(20);
  });

  it("Inactive contributors drop out of the aggregate", () => {
    // gmean of just (0.1, 0.4) = 0.2 — the Inactive's fitted_value is
    // ignored even though it's positive.
    const xs = [
      makeCurve({ fitted_value: 0.1 }),
      makeCurve({ fitted_value: 0.4 }),
      makeCurve({ fitted_value: 0.05, curve_class: "inactive" }),
    ];
    expect(aggregateValue(xs, "gmean")).toBeCloseTo(0.2, 3);
  });

  it("non-positive fitted_values drop out (log10 explodes on them)", () => {
    const xs = [
      makeCurve({ fitted_value: 0.1 }),
      makeCurve({ fitted_value: 0 }),
      makeCurve({ fitted_value: -1 }),
    ];
    // Only 0.1 contributes — gmean of a single value is itself.
    expect(aggregateValue(xs, "gmean")).toBeCloseTo(0.1, 6);
  });
});
