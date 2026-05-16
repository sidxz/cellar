import { describe, expect, it } from "vitest";
import {
  AGGREGATION_MODES,
  aggregationModeFromUrl,
  aggregationModeToUrl,
  aggregationModeToWire,
  isAggregationMode,
  wireToAggregationMode,
} from "./use-aggregation-mode";

describe("AggregationMode helpers", () => {
  it("default mode is latest", () => {
    expect(aggregationModeFromUrl(null)).toBe("latest");
    expect(aggregationModeFromUrl("")).toBe("latest");
    expect(aggregationModeFromUrl("garbage")).toBe("latest");
  });

  it("URL <-> mode round-trip", () => {
    for (const mode of AGGREGATION_MODES) {
      expect(aggregationModeFromUrl(aggregationModeToUrl(mode))).toBe(mode);
    }
  });

  it("wire <-> mode round-trip", () => {
    expect(wireToAggregationMode("latest_approved_run")).toBe("latest");
    expect(wireToAggregationMode("geometric_mean")).toBe("gmean");
    expect(wireToAggregationMode("mean_across_runs")).toBe("mean");
    expect(wireToAggregationMode("best_r_squared")).toBe("best_r2");

    expect(aggregationModeToWire("latest")).toBe("latest_approved_run");
    expect(aggregationModeToWire("gmean")).toBe("geometric_mean");
    expect(aggregationModeToWire("mean")).toBe("mean_across_runs");
    expect(aggregationModeToWire("best_r2")).toBe("best_r_squared");
  });

  it("isAggregationMode narrows correctly", () => {
    expect(isAggregationMode("latest")).toBe(true);
    expect(isAggregationMode("gmean")).toBe(true);
    expect(isAggregationMode("nonsense")).toBe(false);
  });
});
