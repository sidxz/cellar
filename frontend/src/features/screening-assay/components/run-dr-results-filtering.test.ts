import { describe, expect, it } from "vitest";
import type { InterceptSpec } from "../types";
import { type RunPotencyFilter, matchesRunViewFilters } from "./run-dr-results-filtering";
import type { CompoundCurveRow } from "./run-dr-results-transforms";

const primary: InterceptSpec = { kind: "ec", level: 50, basis: "relative_percent", label: null };
const secondary: InterceptSpec = { ...primary, level: 90 };
const row = {
  fitted_value: 0.001,
  fitted_unit: "uM",
  curve_class: "full",
  data_points: [
    { x: 0.0002, y: 10 },
    { x: 100, y: 100 },
  ],
  intercept_values: [{ spec: primary, value: 0.001, qualifier: "=" }],
} as CompoundCurveRow;
const filter = (patch: Partial<RunPotencyFilter> = {}): RunPotencyFilter => ({
  spec: primary,
  primary: true,
  operator: "lte",
  threshold: 1,
  unit: "nM",
  ...patch,
});

describe("run table view filters", () => {
  it("selects classes by their actual identity, including unclassified results", () => {
    expect(matchesRunViewFilters(row, ["full", "partial"], null)).toBe(true);
    expect(matchesRunViewFilters(row, ["inactive"], null)).toBe(false);
    expect(matchesRunViewFilters({ ...row, curve_class: null }, ["unclassified"], null)).toBe(true);
    expect(matchesRunViewFilters({ ...row, curve_class: null }, [], null)).toBe(true);
  });
  it("compares concentrations across display units without changing the source value", () => {
    expect(matchesRunViewFilters(row, [], filter())).toBe(true);
    expect(matchesRunViewFilters(row, [], filter({ operator: "lt" }))).toBe(false);
    expect(matchesRunViewFilters(row, [], filter({ threshold: 0.001, unit: "uM" }))).toBe(true);
    expect(row.fitted_value).toBe(0.001);
  });
  it("does not treat a below-range result as an exact or infinitely potent value", () => {
    const below = { ...row, curve_class: "active_all_doses" as const };
    expect(matchesRunViewFilters(below, [], filter({ threshold: 1 }))).toBe(true);
    expect(matchesRunViewFilters(below, [], filter({ threshold: 0.1 }))).toBe(false);
    expect(matchesRunViewFilters(below, [], filter({ operator: "gte", threshold: 0.1 }))).toBe(
      false,
    );
  });
  it("only includes above-range results when their bound guarantees the comparison", () => {
    const above = { ...row, curve_class: "inactive" as const };
    expect(
      matchesRunViewFilters(above, [], filter({ operator: "gt", threshold: 50, unit: "uM" })),
    ).toBe(true);
    expect(
      matchesRunViewFilters(above, [], filter({ operator: "lt", threshold: 200, unit: "uM" })),
    ).toBe(false);
  });
  it("never borrows the primary value for a missing or ND secondary endpoint", () => {
    const secondaryFilter = filter({ spec: secondary, primary: false });
    expect(matchesRunViewFilters(row, [], secondaryFilter)).toBe(false);
    const nd = {
      ...row,
      intercept_values: [
        ...(row.intercept_values ?? []),
        {
          spec: secondary,
          value: null,
          qualifier: "nd" as const,
          at_bound: false,
          confidence_interval_low: null,
          confidence_interval_high: null,
        },
      ],
    };
    expect(matchesRunViewFilters(nd, [], secondaryFilter)).toBe(false);
  });
  it("preserves a stored qualifier when a legacy protocol has no intercept definitions", () => {
    const legacy = {
      ...row,
      intercept_values: [
        {
          spec: primary,
          value: 0.0002,
          qualifier: "<" as const,
          at_bound: false,
          confidence_interval_low: null,
          confidence_interval_high: null,
        },
      ],
    };
    expect(matchesRunViewFilters(legacy, [], filter({ spec: null, threshold: 0.1 }))).toBe(false);
    expect(matchesRunViewFilters(legacy, [], filter({ spec: null, threshold: 1 }))).toBe(true);
  });
  it("does not compare incompatible concentration units", () => {
    expect(matchesRunViewFilters({ ...row, fitted_unit: "mg/mL" }, [], filter())).toBe(false);
  });
});
