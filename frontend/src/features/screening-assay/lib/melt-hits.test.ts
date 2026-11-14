import { describe, expect, it } from "vitest";

import type { HitCriterion, MeltingAnalysis, ReadoutDefinition } from "../types";
import type { CurvePosition } from "./curve-plot";
import {
  bandFor,
  hitWells,
  isSeriesReadout,
  meetsRule,
  runRulesOf,
  splitRunRules,
} from "./melt-hits";

const rule = (
  readout_name: string,
  operator: HitCriterion["operator"],
  value: HitCriterion["value"],
): HitCriterion => ({ readout_name, operator, value, intercept_key: null });

const outside = (name: string, lo = -2, hi = 2) => rule(name, "not_between", [lo, hi]);

const melt = (name: string, window: string, measure: string, channel = "ratio") =>
  ({
    name,
    melt_config: { window, measure, channel_key: channel, low: 0, high: 100 },
    dose_response_config: null,
  }) as unknown as ReadoutDefinition;

const READOUTS = [
  melt("Tm (Main)", "Main", "tm"),
  melt("ΔTm (Main)", "Main", "delta_tm"),
  melt("ΔTm (Low)", "Low", "delta_tm"),
  melt("ΔTm (350)", "Other signal", "delta_tm", "350nm"),
  melt("Max ΔTm (Main)", "Main", "max_delta_tm"),
  { name: "Inhibition", melt_config: null } as unknown as ReadoutDefinition,
];

const pos = (well_id: string, well_type = "sample") =>
  ({ well_id, well_type }) as unknown as CurvePosition;
const POSITIONS = [
  pos("ref", "reference"),
  pos("s1"),
  pos("s2"),
  pos("s3"),
  pos("c1", "positive_control"),
];

const cell = (well_id: string, tm: number | null, delta_tm: number | null) => ({
  well_id,
  tm,
  delta_tm,
  flags: [],
});
function analysis(windows: Record<string, ReturnType<typeof cell>[]>): MeltingAnalysis {
  return {
    run_id: "r",
    edit_refusal: null,
    steps: [],
    step_checks: [],
    windows: Object.entries(windows).map(([window, positions]) => ({
      window,
      channel_key: window === "Other signal" ? "350nm" : "ratio",
      low: 0,
      high: 100,
      tm_readout_id: null,
      delta_tm_readout_id: null,
      reference_tm: 71.3,
      reference_count: 1,
      flags: [],
      positions,
      series: [],
    })),
  } as MeltingAnalysis;
}

describe("meetsRule", () => {
  it.each([
    [outside("x"), -2, false],
    [outside("x"), -2.1, true],
    [outside("x"), 2, false],
    [outside("x"), 2.01, true],
    [outside("x"), 0, false],
    [rule("x", "gt", 2), 2, false],
    [rule("x", "gte", 2), 2, true],
    [rule("x", "lt", -2), -3, true],
    [rule("x", "lte", -2), -2, true],
    [rule("x", "in", ["full"]), 5, false],
  ])("%j on %d → %s", (r, v, expected) => {
    expect(meetsRule(v, r)).toBe(expected);
  });
});

describe("isSeriesReadout", () => {
  it("is true only for per-batch measures", () => {
    expect(READOUTS.map(isSeriesReadout)).toEqual([false, false, false, false, true, false]);
  });
});

describe("splitRunRules", () => {
  it("applies rules on per-position melt readouts and sets the rest aside", () => {
    const rules = [
      outside("ΔTm (Main)"),
      rule("Inhibition", "gt", 50),
      rule("Gone readout", "gt", 1),
      rule("Max ΔTm (Main)", "lt", -2),
    ];
    const { applicable, other } = splitRunRules(rules, READOUTS);
    expect(applicable).toEqual([{ rule: rules[0], window: "Main", measure: "delta_tm" }]);
    expect(other).toEqual([rules[1], rules[2], rules[3]]);
  });
});

describe("hitWells", () => {
  const data = analysis({
    Main: [
      cell("ref", 71.3, null),
      cell("s1", 62.7, -8.6),
      cell("s2", 70.5, -0.8),
      cell("s3", null, null),
      cell("c1", 60, -11.3),
    ],
    Low: [cell("s1", 30, 3), cell("s2", 30, 3)],
    "Other signal": [cell("s2", 80, 9)],
  });

  it("is empty without an applicable rule", () => {
    expect(hitWells(data, POSITIONS, []).size).toBe(0);
  });

  it("calls samples only, and a missing value is no hit", () => {
    const { applicable } = splitRunRules([outside("ΔTm (Main)")], READOUTS);
    expect([...hitWells(data, POSITIONS, applicable)]).toEqual(["s1"]);
  });

  it("requires every applicable rule (AND)", () => {
    const { applicable } = splitRunRules([outside("ΔTm (Main)"), outside("ΔTm (Low)")], READOUTS);
    expect([...hitWells(data, POSITIONS, applicable)]).toEqual(["s1"]);
    const { applicable: tmToo } = splitRunRules(
      [outside("ΔTm (Main)"), rule("Tm (Main)", "gt", 65)],
      READOUTS,
    );
    expect(hitWells(data, POSITIONS, tmToo).size).toBe(0);
  });

  it("evaluates a window on another signal than the one on screen", () => {
    const { applicable } = splitRunRules([rule("ΔTm (350)", "gt", 5)], READOUTS);
    expect([...hitWells(data, POSITIONS, applicable)]).toEqual(["s2"]);
  });
});

describe("bandFor", () => {
  const split = (r: HitCriterion) => splitRunRules([r], READOUTS).applicable;
  it("draws the outside band from a not_between rule on the window's ΔTm", () => {
    expect(bandFor(split(outside("ΔTm (Main)", -3, 2)), "Main")).toEqual({
      kind: "outside",
      low: -3,
      high: 2,
    });
  });
  it("draws a line for a one-sided rule", () => {
    expect(bandFor(split(rule("ΔTm (Main)", "gte", 2)), "Main")).toEqual({ kind: "line", at: 2 });
    expect(bandFor(split(rule("ΔTm (Main)", "lt", -1.5)), "Main")).toEqual({
      kind: "line",
      at: -1.5,
    });
  });
  it("has no band for another window or a rule on Tm", () => {
    expect(bandFor(split(outside("ΔTm (Main)")), "Low")).toBeNull();
    expect(bandFor(split(rule("Tm (Main)", "gt", 60)), "Main")).toBeNull();
  });
});

describe("runRulesOf", () => {
  it("keeps what a run may record and sets series values aside", () => {
    const series = rule("Max ΔTm (Main)", "lt", -5);
    const plain = rule("Inhibition", "gt", 50);
    expect(runRulesOf([outside("ΔTm (Main)"), series, plain], READOUTS)).toEqual({
      kept: [outside("ΔTm (Main)"), plain],
      dropped: [series],
    });
  });
});
