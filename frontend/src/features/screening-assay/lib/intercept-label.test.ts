import { describe, expect, it } from "vitest";
import type { InterceptKey, InterceptSpec, InterceptValue } from "../types";
import {
  doseRange,
  findInterceptValue,
  formatInterceptDisplay,
  interceptKeyId,
  interceptKeyLabel,
  interceptLabel,
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

describe("doseRange", () => {
  it("reads the lowest and highest positive dose from {x,y} points", () => {
    expect(
      doseRange([
        { x: 0.1, y: 5 },
        { x: 10, y: 80 },
        { x: 1, y: 40 },
      ]),
    ).toEqual({ min_dose: 0.1, max_dose: 10 });
  });

  it("accepts {concentration, response} shape too", () => {
    expect(
      doseRange([
        { concentration: 0.5, response: 10 },
        { concentration: 50, response: 90 },
      ]),
    ).toEqual({ min_dose: 0.5, max_dose: 50 });
  });

  it("ignores non-positive and non-finite x", () => {
    expect(
      doseRange([
        { x: -1, y: 5 },
        { x: 0, y: 5 },
        { x: Number.NaN, y: 5 },
        { x: 7, y: 5 },
      ]),
    ).toEqual({ min_dose: 7, max_dose: 7 });
  });

  it("returns nulls on empty / nullish input", () => {
    const none = { min_dose: null, max_dose: null };
    expect(doseRange(null)).toEqual(none);
    expect(doseRange(undefined)).toEqual(none);
    expect(doseRange([])).toEqual(none);
  });
});

describe("formatInterceptDisplay", () => {
  it("reads an inactive curve as above its top dose, whatever the fit's value", () => {
    // Run 394e4741's SACC-0108241: inactive over 0.5–500 µM, fit parked at 1172.
    const out = formatInterceptDisplay({
      value: 1172.1,
      at_bound: false,
      curve_class: "inactive",
      min_dose: 0.5,
      max_dose: 500,
    });
    expect(out.kind).toBe("qualifier");
    expect(out.text).toBe("> 500");
    expect(out.warning).toBe(false);
    expect(out.tooltip).toMatch(/inactive/i);
    expect(out.sortValue).toBe(Number.POSITIVE_INFINITY);
  });

  it("returns ND for an inactive curve with no tested dose to report", () => {
    const out = formatInterceptDisplay({
      value: 0.013,
      at_bound: false,
      curve_class: "inactive",
      max_dose: null,
    });
    expect(out.kind).toBe("nd");
    expect(out.text).toBe("ND");
    expect(out.tooltip).toMatch(/not determined/i);
    expect(out.sortValue).toBeNull();
  });

  it("reads a value fitted above the top dose as above it, not the extrapolated number", () => {
    const out = formatInterceptDisplay({
      value: 1172.1,
      at_bound: false,
      curve_class: "partial",
      min_dose: 0.5,
      max_dose: 500,
    });
    expect(out.kind).toBe("qualifier");
    expect(out.text).toBe("> 500");
    expect(out.warning).toBe(true);
    expect(out.sortValue).toBe(Number.POSITIVE_INFINITY);
  });

  it("reads a value fitted below the lowest dose as below it", () => {
    const out = formatInterceptDisplay({
      value: 0.0002,
      at_bound: false,
      curve_class: "full",
      min_dose: 0.0006,
      max_dose: 2,
    });
    expect(out.kind).toBe("qualifier");
    expect(out.text).toBe("< 0.0006");
    expect(out.warning).toBe(true);
    expect(out.sortValue).toBe(Number.NEGATIVE_INFINITY);
  });

  it("keeps a value inside the tested doses as the number (rifampicin, EC50 0.00122 µM)", () => {
    const out = formatInterceptDisplay({
      value: 0.0012230246,
      at_bound: false,
      curve_class: "full",
      min_dose: 0.0006,
      max_dose: 2,
    });
    expect(out.kind).toBe("scalar");
    expect(out.text).toBe("0.001223");
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
    expect(out.text).toBe("> 50");
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
      value: 0.0131,
      at_bound: false,
      curve_class: "full",
      max_dose: 50,
    });
    expect(out.kind).toBe("scalar");
    expect(out.text).toBe("0.01310");
    expect(out.warning).toBe(false);
    expect(out.sortValue).toBe(0.0131);
  });

  it("inactive overrides at_bound (worst signal wins)", () => {
    const out = formatInterceptDisplay({
      value: 0.0001,
      at_bound: true,
      curve_class: "inactive",
      max_dose: 50,
    });
    expect(out.tooltip).toMatch(/inactive/i);
    expect(out.warning).toBe(false);
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
      at_bound: true,
      curve_class: "full",
      max_dose: null,
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

describe("formatInterceptDisplay multi-run extension", () => {
  // The function's existing 4-input shape stays valid; these tests
  // exercise the new optional inputs (runCount, mode, foldRange, disagreement)
  // and the new outputs (primary alias, decoration).

  it("primary aliases text for scalar cells", () => {
    const out = formatInterceptDisplay({
      value: 0.12,
      at_bound: false,
      curve_class: "active",
      max_dose: 100,
    });
    expect(out.primary).toBe(out.text);
    expect(out.primary).toBe("0.1200");
  });

  it("decoration is null for single-run cells", () => {
    const out = formatInterceptDisplay({
      value: 0.12,
      at_bound: false,
      curve_class: "active",
      max_dose: 100,
    });
    expect(out.decoration).toBeNull();
  });

  it("adds run-count subscript when runCount >= 2", () => {
    const out = formatInterceptDisplay({
      value: 0.18,
      at_bound: false,
      curve_class: "active",
      max_dose: 100,
      runCount: 3,
    });
    expect(out.decoration?.runCountSubscript).toBe("₃");
    expect(out.decoration?.foldRangeChip).toBeNull();
  });

  it("adds fold-range chip in gmean mode but not in latest mode", () => {
    const gmean = formatInterceptDisplay({
      value: 0.18,
      at_bound: false,
      curve_class: "active",
      max_dose: 100,
      runCount: 4,
      mode: "gmean",
      foldRange: 4.2,
    });
    expect(gmean.decoration?.foldRangeChip).toBe("×4");

    const latest = formatInterceptDisplay({
      value: 0.18,
      at_bound: false,
      curve_class: "active",
      max_dose: 100,
      runCount: 4,
      mode: "latest",
      foldRange: 4.2,
    });
    expect(latest.decoration?.foldRangeChip).toBeNull();
  });

  it("warning triggers when disagreement true (even on scalar cell)", () => {
    const out = formatInterceptDisplay({
      value: 0.18,
      at_bound: false,
      curve_class: "active",
      max_dose: 100,
      disagreement: true,
    });
    expect(out.warning).toBe(true);
  });

  it("warning still triggers on qualifier cells regardless of disagreement", () => {
    const out = formatInterceptDisplay({
      value: 0.0001,
      at_bound: true,
      curve_class: "active",
      max_dose: 100,
      disagreement: false,
    });
    expect(out.kind).toBe("qualifier");
    expect(out.warning).toBe(true); // qualifier always warns
  });

  it("subscript renders for multi-digit run counts", () => {
    const out = formatInterceptDisplay({
      value: 0.18,
      at_bound: false,
      curve_class: "active",
      max_dose: 100,
      runCount: 12,
    });
    expect(out.decoration?.runCountSubscript).toBe("₁₂");
  });
});

describe("formatInterceptDisplay — stored qualifier", () => {
  const range = { max_dose: 100, min_dose: 0.0002 };
  const show = (over: Partial<Parameters<typeof formatInterceptDisplay>[0]>) =>
    formatInterceptDisplay({ value: 1, at_bound: false, curve_class: "full", ...range, ...over });

  it("reads an Active-at-all-doses curve as below the lowest dose, whatever it stored", () => {
    for (const qualifier of ["<", "=", ">", "nd", null] as const) {
      const out = show({ curve_class: "active_all_doses", qualifier, value: 0.0002 });
      expect(out.text).toBe("< 0.0002");
      expect(out.sortValue).toBe(Number.NEGATIVE_INFINITY);
    }
  });

  it("keeps an inactive curve above the top dose even when it stored an exact value", () => {
    expect(show({ curve_class: "inactive", qualifier: "=", value: 3 }).text).toBe("> 100");
  });

  it("reports a censored value at the edge of the tested doses as a bound", () => {
    expect(show({ qualifier: "<", value: 0.0002 }).text).toBe("< 0.0002");
    expect(show({ qualifier: ">", value: 100 }).text).toBe("> 100");
  });

  it("says a value the flat curve cannot give is not determined, not missing", () => {
    const out = show({ qualifier: "nd", value: null });
    expect(out.kind).toBe("nd");
    expect(out.text).toBe("ND");
  });

  it("shows an exact value as a number", () => {
    const out = show({ qualifier: "=", value: 3.87 });
    expect(out.kind).toBe("scalar");
    expect(out.text).toBe("3.870");
  });

  it("keeps today's display for a curve stored before qualifiers", () => {
    expect(show({ value: 0.00001 }).text).toBe("< 0.0002");
    expect(show({ value: null }).kind).toBe("missing");
    expect(show({ value: 3.87 }).text).toBe("3.870");
  });
});
