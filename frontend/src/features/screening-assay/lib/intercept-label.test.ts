import { describe, expect, it } from "vitest";
import type { InterceptKey, InterceptSpec, InterceptValue } from "../types";
import {
  findInterceptValue,
  formatInterceptDisplay,
  interceptKeyId,
  interceptKeyLabel,
  interceptLabel,
  maxDoseFromRawData,
  parseInterceptKeyId,
} from "./intercept-label";

function spec(over: Partial<InterceptSpec> = {}): InterceptSpec {
  return {
    kind: "ec",
    level: 50,
    basis: "relative_percent",
    label: null,
    ...over,
  };
}

function value(over: Partial<InterceptValue> = {}): InterceptValue {
  return {
    spec: spec(),
    value: 1.0,
    confidence_interval_low: null,
    confidence_interval_high: null,
    at_bound: false,
    ...over,
  };
}

describe("interceptLabel", () => {
  it("uses spec.label verbatim when set", () => {
    expect(interceptLabel(spec({ label: "Potency" }))).toBe("Potency");
  });

  it("falls back to KIND+LEVEL when label is null", () => {
    expect(interceptLabel(spec({ kind: "ec", level: 50, label: null }))).toBe("EC50");
    expect(interceptLabel(spec({ kind: "ic", level: 90, label: null }))).toBe("IC90");
  });

  it("falls back to KIND+LEVEL when label is undefined", () => {
    expect(interceptLabel(spec({ kind: "ec", level: 90, label: undefined }))).toBe("EC90");
  });

  it("strips trailing .0 from integer levels", () => {
    expect(interceptLabel(spec({ kind: "ic", level: 50, label: null }))).toBe("IC50");
  });

  it("keeps decimal precision on non-integer levels", () => {
    expect(interceptLabel(spec({ kind: "ec", level: 12.5, label: null }))).toBe("EC12.5");
  });
});

describe("findInterceptValue", () => {
  it("matches by (kind, level) regardless of label drift", () => {
    const protocolSpec = spec({ kind: "ec", level: 90, label: "EC90 (updated label)" });
    const oldValues = [
      value({ spec: spec({ kind: "ec", level: 50, label: "EC50" }), value: 13.7 }),
      // Curve stored the *old* label; protocol later relabeled it.
      value({ spec: spec({ kind: "ec", level: 90, label: "EC90 (old)" }), value: 58.4 }),
    ];
    expect(findInterceptValue(oldValues, protocolSpec)?.value).toBe(58.4);
  });

  it("returns undefined when the curve has no matching intercept", () => {
    const protocolSpec = spec({ kind: "ec", level: 90 });
    const legacyValues = [
      value({ spec: spec({ kind: "ec", level: 50 }), value: 13.7 }),
      // No EC90 — legacy curve fit before protocol added it.
    ];
    expect(findInterceptValue(legacyValues, protocolSpec)).toBeUndefined();
  });

  it("returns undefined when the curve carries no intercepts at all", () => {
    expect(findInterceptValue(null, spec())).toBeUndefined();
    expect(findInterceptValue(undefined, spec())).toBeUndefined();
    expect(findInterceptValue([], spec())).toBeUndefined();
  });

  it("does not collide across kinds at the same level", () => {
    const values = [
      value({ spec: spec({ kind: "ic", level: 50 }), value: 1.1 }),
      value({ spec: spec({ kind: "ec", level: 50 }), value: 2.2 }),
    ];
    expect(findInterceptValue(values, spec({ kind: "ic", level: 50 }))?.value).toBe(1.1);
    expect(findInterceptValue(values, spec({ kind: "ec", level: 50 }))?.value).toBe(2.2);
  });
});

describe("interceptKeyLabel", () => {
  it("renders KIND+LEVEL from a bare key (no protocol-side label)", () => {
    expect(interceptKeyLabel({ kind: "ec", level: 50 } as InterceptKey)).toBe("EC50");
    expect(interceptKeyLabel({ kind: "ic", level: 90 } as InterceptKey)).toBe("IC90");
  });

  it("strips trailing .0 from integer levels and keeps non-integers", () => {
    expect(interceptKeyLabel({ kind: "ec", level: 50 } as InterceptKey)).toBe("EC50");
    expect(interceptKeyLabel({ kind: "ec", level: 12.5 } as InterceptKey)).toBe("EC12.5");
  });
});

describe("interceptKeyId / parseInterceptKeyId", () => {
  it("round-trips ec / ic kinds", () => {
    expect(parseInterceptKeyId(interceptKeyId({ kind: "ec", level: 50 }))).toEqual({
      kind: "ec",
      level: 50,
    });
    expect(parseInterceptKeyId(interceptKeyId({ kind: "ic", level: 90 }))).toEqual({
      kind: "ic",
      level: 90,
    });
  });

  it("returns null for malformed or unknown-kind ids", () => {
    expect(parseInterceptKeyId(undefined)).toBeNull();
    expect(parseInterceptKeyId("")).toBeNull();
    expect(parseInterceptKeyId("primary")).toBeNull();
    expect(parseInterceptKeyId("xx:50")).toBeNull();
    expect(parseInterceptKeyId("ec:nope")).toBeNull();
  });
});

describe("maxDoseFromRawData", () => {
  it("returns the largest positive x from {x,y} points", () => {
    expect(
      maxDoseFromRawData([
        { x: 0.1, y: 5 },
        { x: 10, y: 80 },
        { x: 1, y: 40 },
      ] as unknown as Array<{ x?: number; concentration?: number }>),
    ).toBe(10);
  });

  it("accepts {concentration, response} shape too", () => {
    expect(
      maxDoseFromRawData([
        { concentration: 0.5, response: 10 },
        { concentration: 50, response: 90 },
      ] as unknown as Array<{ x?: number; concentration?: number }>),
    ).toBe(50);
  });

  it("ignores non-positive and non-finite x", () => {
    expect(
      maxDoseFromRawData([
        { x: -1, y: 5 },
        { x: 0, y: 5 },
        { x: Number.NaN, y: 5 },
        { x: 7, y: 5 },
      ] as unknown as Array<{ x?: number; concentration?: number }>),
    ).toBe(7);
  });

  it("returns null on empty / nullish input", () => {
    expect(maxDoseFromRawData(null)).toBeNull();
    expect(maxDoseFromRawData(undefined)).toBeNull();
    expect(maxDoseFromRawData([])).toBeNull();
  });
});

describe("formatInterceptDisplay", () => {
  it("returns ND for inactive class regardless of value/at_bound", () => {
    const out = formatInterceptDisplay({
      value: 0.013,
      at_bound: false,
      curve_class: "inactive",
      max_dose: 50,
    });
    expect(out.kind).toBe("nd");
    expect(out.text).toBe("ND");
    expect(out.warning).toBe(false);
    expect(out.tooltip).toMatch(/not determined/i);
    expect(out.sortValue).toBeNull();
  });

  it("returns '—' for missing value when class is not inactive", () => {
    const out = formatInterceptDisplay({
      value: null,
      at_bound: false,
      curve_class: "full",
      max_dose: 50,
    });
    expect(out.kind).toBe("missing");
    expect(out.text).toBe("—");
    expect(out.warning).toBe(false);
    expect(out.sortValue).toBeNull();
  });

  it("returns qualifier when at_bound with a known max_dose", () => {
    const out = formatInterceptDisplay({
      value: 0.0001,
      at_bound: true,
      curve_class: "full",
      max_dose: 50,
    });
    expect(out.kind).toBe("qualifier");
    expect(out.text).toBe("> 50.00");
    expect(out.warning).toBe(true);
    expect(out.tooltip).toMatch(/upper-bound|tested concentration|did not reach/i);
    expect(out.sortValue).toBe(Number.POSITIVE_INFINITY);
  });

  it("falls back to ND when at_bound but max_dose is unavailable", () => {
    const out = formatInterceptDisplay({
      value: 0.0001,
      at_bound: true,
      curve_class: "full",
      max_dose: null,
    });
    expect(out.kind).toBe("nd");
    expect(out.text).toBe("ND");
    expect(out.sortValue).toBeNull();
  });

  it("returns scalar with toPrecision(4) on a healthy fit", () => {
    const out = formatInterceptDisplay({
      value: 0.01310,
      at_bound: false,
      curve_class: "full",
      max_dose: 50,
    });
    expect(out.kind).toBe("scalar");
    expect(out.text).toBe("0.01310");
    expect(out.warning).toBe(false);
    expect(out.sortValue).toBe(0.01310);
  });

  it("inactive overrides at_bound (worst signal wins)", () => {
    const out = formatInterceptDisplay({
      value: 0.0001,
      at_bound: true,
      curve_class: "inactive",
      max_dose: 50,
    });
    expect(out.kind).toBe("nd");
    expect(out.sortValue).toBeNull();
  });

  // Chemist's sort expectation: scalars in ascending potency, then
  // qualifier rows (some response, weaker than tested range), then
  // ND/missing at the bottom. AG Grid puts nulls last in asc by default,
  // so this all falls out of the sortValue numeric ordering.
  it("orders sortValues so chemist-sort works: scalar < qualifier < nd/missing", () => {
    const scalar = formatInterceptDisplay({
      value: 0.5,
      at_bound: false,
      curve_class: "full",
      max_dose: 50,
    }).sortValue;
    const qualifier = formatInterceptDisplay({
      value: 0.001,
      at_bound: true,
      curve_class: "full",
      max_dose: 50,
    }).sortValue;
    const nd = formatInterceptDisplay({
      value: 0.013,
      at_bound: false,
      curve_class: "inactive",
      max_dose: 50,
    }).sortValue;
    const missing = formatInterceptDisplay({
      value: null,
      at_bound: false,
      curve_class: "full",
      max_dose: 50,
    }).sortValue;

    expect(scalar).toBe(0.5);
    expect(qualifier).toBe(Number.POSITIVE_INFINITY);
    expect(nd).toBeNull();
    expect(missing).toBeNull();
    // scalar < qualifier in ascending numeric order
    expect((scalar as number) < (qualifier as number)).toBe(true);
  });
});
