import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { CurveDetail, RunScope } from "../types";
import {
  aggregateValue,
  filterCurvesByRunScope,
  pickRepresentative,
} from "./compound-detail-selection";

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
    const xs = [makeCurve({ fitted_value: 0.1 }), makeCurve({ fitted_value: 0.4 })];
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

// ─── filterCurvesByRunScope ────────────────────────────────────────────────
// Twin of the BE's curve filtering applied via RunScope. Lets the search
// detail drawer narrow its per-protocol curve list to exactly the runs the
// search criterion's `run_scope` allowed — so the drawer chart agrees with
// the grid cell that came from `enrich_molecules` filtering by the same
// scope.
describe("filterCurvesByRunScope", () => {
  const r1 = "00000000-0000-0000-0000-000000000001";
  const r2 = "00000000-0000-0000-0000-000000000002";
  const r3 = "00000000-0000-0000-0000-000000000003";

  it("returns curves unchanged when scope is undefined", () => {
    const xs = [makeCurve({ run_id: r1, run_date: "2026-05-13" })];
    expect(filterCurvesByRunScope(xs, undefined)).toEqual(xs);
  });

  it("returns curves unchanged for mode='any'", () => {
    const xs = [makeCurve({ run_id: r1, run_date: "2026-05-13" })];
    expect(filterCurvesByRunScope(xs, { mode: "any" })).toEqual(xs);
  });

  it("returns curves unchanged for mode='all'", () => {
    const xs = [makeCurve({ run_id: r1, run_date: "2026-05-13" })];
    expect(filterCurvesByRunScope(xs, { mode: "all" })).toEqual(xs);
  });

  it("mode='specific' (multi-shape) keeps only curves whose run_id is in run_ids", () => {
    const xs = [
      makeCurve({ curve_id: "a", run_id: r1 }),
      makeCurve({ curve_id: "b", run_id: r2 }),
      makeCurve({ curve_id: "c", run_id: r3 }),
    ];
    const out = filterCurvesByRunScope(xs, {
      mode: "specific",
      run_ids: [r1, r3],
    });
    expect(out.map((c) => c.curve_id)).toEqual(["a", "c"]);
  });

  it("mode='specific' (legacy single-shape run_id) keeps only that run", () => {
    const xs = [makeCurve({ curve_id: "a", run_id: r1 }), makeCurve({ curve_id: "b", run_id: r2 })];
    const out = filterCurvesByRunScope(xs, { mode: "specific", run_id: r2 });
    expect(out.map((c) => c.curve_id)).toEqual(["b"]);
  });

  it("mode='specific' with empty selection returns empty (invalid scope = nothing in-scope)", () => {
    const xs = [makeCurve({ run_id: r1 })];
    expect(filterCurvesByRunScope(xs, { mode: "specific", run_ids: [] })).toEqual([]);
  });

  it("mode='latest' keeps only curves from the most recent run", () => {
    // Multi-DR protocol: two curves from the newest run; one from an older
    // run. After filtering we should have both curves from the newest run.
    const xs = [
      makeCurve({ curve_id: "old", run_id: r1, run_date: "2026-05-13" }),
      makeCurve({ curve_id: "new-a", run_id: r2, run_date: "2026-05-15" }),
      makeCurve({ curve_id: "new-b", run_id: r2, run_date: "2026-05-15" }),
    ];
    const out = filterCurvesByRunScope(xs, { mode: "latest" });
    expect(out.map((c) => c.curve_id).sort()).toEqual(["new-a", "new-b"]);
  });

  it("mode='latest' with all null run_dates returns empty (defensive — no way to pick a winner)", () => {
    const xs = [
      makeCurve({ run_id: r1, run_date: null }),
      makeCurve({ run_id: r2, run_date: null }),
    ];
    expect(filterCurvesByRunScope(xs, { mode: "latest" })).toEqual([]);
  });

  describe("mode='past_n_days'", () => {
    // Pin the wall-clock so the relative threshold is deterministic.
    beforeEach(() => {
      vi.useFakeTimers();
      vi.setSystemTime(new Date("2026-05-16T12:00:00Z"));
    });
    afterEach(() => {
      vi.useRealTimers();
    });

    it("keeps curves whose run_date is within the past N days (inclusive)", () => {
      const xs = [
        makeCurve({ curve_id: "old", run_date: "2026-04-01" }), // 45d old
        makeCurve({ curve_id: "edge", run_date: "2026-04-16" }), // exactly 30d
        makeCurve({ curve_id: "fresh", run_date: "2026-05-13" }), // 3d old
      ];
      const out = filterCurvesByRunScope(xs, {
        mode: "past_n_days",
        days: 30,
      });
      expect(out.map((c) => c.curve_id).sort()).toEqual(["edge", "fresh"]);
    });

    it("drops curves with null run_date", () => {
      const xs = [makeCurve({ run_date: null })];
      expect(filterCurvesByRunScope(xs, { mode: "past_n_days", days: 30 })).toEqual([]);
    });
  });

  describe("mode='date_range'", () => {
    it("with both bounds applies them inclusively", () => {
      const xs = [
        makeCurve({ curve_id: "before", run_date: "2026-04-30" }),
        makeCurve({ curve_id: "from", run_date: "2026-05-01" }),
        makeCurve({ curve_id: "mid", run_date: "2026-05-10" }),
        makeCurve({ curve_id: "to", run_date: "2026-05-15" }),
        makeCurve({ curve_id: "after", run_date: "2026-05-16" }),
      ];
      const out = filterCurvesByRunScope(xs, {
        mode: "date_range",
        date_from: "2026-05-01",
        date_to: "2026-05-15",
      });
      expect(out.map((c) => c.curve_id).sort()).toEqual(["from", "mid", "to"]);
    });

    it("with only date_from acts as a lower bound", () => {
      const xs = [
        makeCurve({ curve_id: "before", run_date: "2026-04-30" }),
        makeCurve({ curve_id: "after", run_date: "2026-05-15" }),
      ];
      const out = filterCurvesByRunScope(xs, {
        mode: "date_range",
        date_from: "2026-05-01",
      });
      expect(out.map((c) => c.curve_id)).toEqual(["after"]);
    });

    it("with only date_to acts as an upper bound", () => {
      const xs = [
        makeCurve({ curve_id: "before", run_date: "2026-04-30" }),
        makeCurve({ curve_id: "after", run_date: "2026-05-15" }),
      ];
      const out = filterCurvesByRunScope(xs, {
        mode: "date_range",
        date_to: "2026-05-10",
      });
      expect(out.map((c) => c.curve_id)).toEqual(["before"]);
    });

    it("with neither bound is a no-op (parity with BE RunScope.all())", () => {
      const xs = [makeCurve({ run_date: "2026-05-15" })];
      expect(filterCurvesByRunScope(xs, { mode: "date_range" } as RunScope)).toEqual(xs);
    });

    it("drops curves with null run_date when a bound exists", () => {
      const xs = [
        makeCurve({ curve_id: "null", run_date: null }),
        makeCurve({ curve_id: "ok", run_date: "2026-05-10" }),
      ];
      expect(
        filterCurvesByRunScope(xs, {
          mode: "date_range",
          date_from: "2026-05-01",
        }),
      ).toEqual([xs[1]]);
    });
  });
});
