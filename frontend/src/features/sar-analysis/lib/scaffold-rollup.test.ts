import { describe, expect, it } from "vitest";
import { classifyActivity, medianPic50ForMols } from "./scaffold-rollup";

// Use the loose ActivityData shape — the type test exists so consumers can adapt.
type LooseActivityData = Record<
  string,
  Record<
    string,
    {
      intercept_values?: { kind: string; level: number; value: number | null; qualifier: string }[];
    }
  >
>;

describe("medianPic50ForMols", () => {
  const activity: LooseActivityData = {
    m1: {
      "proto-A": { intercept_values: [{ kind: "ec", level: 50, value: 1e-6, qualifier: "=" }] },
    },
    m2: {
      "proto-A": { intercept_values: [{ kind: "ec", level: 50, value: 1e-7, qualifier: "=" }] },
    },
    m3: {
      "proto-A": { intercept_values: [{ kind: "ec", level: 50, value: null, qualifier: "nd" }] },
    },
    m4: {
      "proto-A": { intercept_values: [{ kind: "ec", level: 50, value: 1e-8, qualifier: "=" }] },
    },
  };

  it("computes median pIC50 (excludes ND)", () => {
    // pIC50 values: 6, 7, 8 (m3 ND excluded). Median = 7.
    const v = medianPic50ForMols(["m1", "m2", "m3", "m4"], activity as any, "proto-A");
    expect(v).toBeCloseTo(7, 5);
  });

  it("median of 2 values is the average", () => {
    const v = medianPic50ForMols(["m1", "m4"], activity as any, "proto-A");
    // 6, 8 -> 7
    expect(v).toBeCloseTo(7, 5);
  });

  it("returns null when mol has no protocol entry", () => {
    expect(medianPic50ForMols(["mX"], activity as any, "proto-A")).toBeNull();
  });

  it("returns null when all values are ND", () => {
    expect(medianPic50ForMols(["m3"], activity as any, "proto-A")).toBeNull();
  });

  it("excludes value <= 0 (log undefined)", () => {
    const bad: LooseActivityData = {
      m1: { p: { intercept_values: [{ kind: "ec", level: 50, value: 0, qualifier: "=" }] } },
      m2: { p: { intercept_values: [{ kind: "ec", level: 50, value: -1, qualifier: "=" }] } },
    };
    expect(medianPic50ForMols(["m1", "m2"], bad as any, "p")).toBeNull();
  });
});

describe("classifyActivity", () => {
  it("classifies into 4 bins", () => {
    expect(classifyActivity(8.5)).toBe("active_high");
    expect(classifyActivity(7)).toBe("active_mid");
    expect(classifyActivity(5.5)).toBe("weak");
    expect(classifyActivity(4)).toBe("inactive");
  });

  it("classifies boundary exactly at threshold", () => {
    expect(classifyActivity(8)).toBe("active_high");
    expect(classifyActivity(6)).toBe("active_mid");
    expect(classifyActivity(5)).toBe("weak");
  });

  it("returns null on null input", () => {
    expect(classifyActivity(null)).toBeNull();
  });

  it("returns null on NaN input", () => {
    expect(classifyActivity(Number.NaN)).toBeNull();
  });
});
