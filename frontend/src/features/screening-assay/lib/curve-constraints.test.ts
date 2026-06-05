import { describe, expect, it } from "vitest";
import { constraintsValid, isRangeValid, parseInputOrNull } from "./curve-constraints";
import type { CurveConstraints } from "./curve-constraints";

// ─── parseInputOrNull ─────────────────────────────────────────────────────────

describe("parseInputOrNull", () => {
  it("returns null for empty string", () => {
    expect(parseInputOrNull("")).toBeNull();
    expect(parseInputOrNull("   ")).toBeNull();
  });

  it("parses valid floats", () => {
    expect(parseInputOrNull("100")).toBe(100);
    expect(parseInputOrNull("0.5")).toBeCloseTo(0.5, 8);
    expect(parseInputOrNull("-10")).toBe(-10);
  });

  it("returns null for non-numeric strings", () => {
    expect(parseInputOrNull("abc")).toBeNull();
    expect(parseInputOrNull("NaN")).toBeNull();
    expect(parseInputOrNull("Infinity")).toBeNull();
  });
});

// ─── isRangeValid ─────────────────────────────────────────────────────────────

describe("isRangeValid", () => {
  it("returns true when min < max and both are finite numbers", () => {
    expect(isRangeValid(0, 100)).toBe(true);
    expect(isRangeValid(-10, 10)).toBe(true);
    expect(isRangeValid(0.9, 1.1)).toBe(true);
  });

  it("returns false when min >= max", () => {
    expect(isRangeValid(100, 0)).toBe(false);
    expect(isRangeValid(50, 50)).toBe(false);
  });

  it("returns false when either value is null", () => {
    expect(isRangeValid(null, 100)).toBe(false);
    expect(isRangeValid(0, null)).toBe(false);
    expect(isRangeValid(null, null)).toBe(false);
  });
});

// ─── constraintsValid ─────────────────────────────────────────────────────────

describe("constraintsValid", () => {
  const FREE_CONSTRAINTS: CurveConstraints = {
    topMode: "free",
    topValue: null,
    topMin: null,
    topMax: null,
    bottomMode: "free",
    bottomValue: null,
    bottomMin: null,
    bottomMax: null,
    hillSlope: "unconstrained",
    hillCustomRange: false,
    hillMin: null,
    hillMax: null,
  };

  it("accepts fully free constraints", () => {
    expect(constraintsValid(FREE_CONSTRAINTS)).toBe(true);
  });

  it("requires topValue when topMode is lock", () => {
    expect(constraintsValid({ ...FREE_CONSTRAINTS, topMode: "lock", topValue: null })).toBe(false);
    expect(constraintsValid({ ...FREE_CONSTRAINTS, topMode: "lock", topValue: 100 })).toBe(true);
  });

  it("requires valid range when topMode is range", () => {
    expect(
      constraintsValid({ ...FREE_CONSTRAINTS, topMode: "range", topMin: null, topMax: null }),
    ).toBe(false);
    expect(
      constraintsValid({ ...FREE_CONSTRAINTS, topMode: "range", topMin: 85, topMax: 80 }),
    ).toBe(false);
    expect(
      constraintsValid({ ...FREE_CONSTRAINTS, topMode: "range", topMin: 85, topMax: 110 }),
    ).toBe(true);
  });

  it("requires valid hillMin/hillMax when hillCustomRange is true", () => {
    expect(
      constraintsValid({
        ...FREE_CONSTRAINTS,
        hillCustomRange: true,
        hillMin: null,
        hillMax: null,
      }),
    ).toBe(false);
    expect(
      constraintsValid({ ...FREE_CONSTRAINTS, hillCustomRange: true, hillMin: 0.9, hillMax: 1.1 }),
    ).toBe(true);
  });
});
