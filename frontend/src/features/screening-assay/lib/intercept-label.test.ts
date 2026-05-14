import { describe, expect, it } from "vitest";
import type { InterceptKey, InterceptSpec, InterceptValue } from "../types";
import {
  findInterceptValue,
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
