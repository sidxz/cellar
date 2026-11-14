import { describe, expect, it } from "vitest";

import type { CompoundActivity, HitCriterion, ReadoutDefInfo } from "../types";
import {
  activityCatalog,
  compareForDirection,
  defaultSortColumn,
  visibleColumnIds,
} from "./activity-columns";

const melt = (
  name: string,
  measure: string,
  extra: Record<string, unknown> = {},
  window = "Main",
): ReadoutDefInfo =>
  ({
    name,
    data_type: "numeric",
    unit: measure === "lowest_shift_concentration" ? "µM" : "°C",
    best_direction: measure === "lowest_shift_concentration" ? "low" : "magnitude",
    intercepts: [],
    melt_config: {
      window,
      measure,
      channel_key: "ratio",
      low: window === "Main" ? 50 : 25,
      high: window === "Main" ? 85 : 50,
      ...extra,
    },
  }) as unknown as ReadoutDefInfo;
const plain = (name: string, unit = "°C"): ReadoutDefInfo =>
  ({ name, data_type: "numeric", unit, best_direction: "high", intercepts: [] }) as ReadoutDefInfo;

const THERMAL = [
  plain("Inflection Point #1 for Ratio"),
  plain("Instrument Tm 2"),
  melt("Tm (Low)", "tm", {}, "Low"),
  melt("ΔTm (Low)", "delta_tm", {}, "Low"),
  melt("Tm (Main)", "tm"),
  melt("ΔTm (Main)", "delta_tm"),
  melt("Max ΔTm (Main)", "max_delta_tm"),
  melt("Lowest shifting conc. (Main, ±2 °C)", "lowest_shift_concentration", { threshold: 2 }),
  melt("ΔTm at 50 µM (Main)", "delta_tm_at_concentration", { concentration: 50 }),
];

const item = (values: Record<string, number | null>): CompoundActivity =>
  ({
    molecule_id: "m",
    readouts: Object.fromEntries(Object.entries(values).map(([k, v]) => [k, { best: v, mean: v }])),
  }) as unknown as CompoundActivity;

const HAS_DATA = [
  item({
    "Inflection Point #1 for Ratio": 70.4,
    "Tm (Main)": 70.4,
    "ΔTm (Main)": -0.9,
    "Max ΔTm (Main)": -0.9,
  }),
];

describe("activityCatalog for a thermal-shift protocol", () => {
  const catalog = activityCatalog(THERMAL, HAS_DATA, []);
  const by = (readout: string) => catalog.find((c) => c.readout === readout)!;

  it("groups a window's readouts under one header with short labels", () => {
    expect(by("Max ΔTm (Main)")).toMatchObject({
      group: "Main window · 50–85 °C",
      label: "Max ΔTm (°C)",
    });
    expect(by("Lowest shifting conc. (Main, ±2 °C)").label).toBe("Lowest shift ±2 °C (µM)");
    expect(by("ΔTm at 50 µM (Main)").label).toBe("ΔTm at 50 µM (°C)");
    expect(by("Tm (Low)").group).toBe("Low window · 25–50 °C");
    expect(by("Instrument Tm 2").group).toBe("Other readouts");
  });

  it("orders a window's series values first", () => {
    const main = catalog.filter((c) => c.group === "Main window · 50–85 °C").map((c) => c.readout);
    expect(main).toEqual([
      "Max ΔTm (Main)",
      "Lowest shifting conc. (Main, ±2 °C)",
      "ΔTm at 50 µM (Main)",
      "ΔTm (Main)",
      "Tm (Main)",
    ]);
  });

  it("shows what a chemist compares on; the rest is on demand", () => {
    expect(by("Max ΔTm (Main)").defaultVisible).toBe(true);
    // A window without series values shows its ΔTm.
    expect(by("ΔTm (Main)").defaultVisible).toBe(false);
    expect(by("Tm (Main)").defaultVisible).toBe(false);
    // Instrument values in a thermal-shift protocol are on demand.
    expect(by("Inflection Point #1 for Ratio").defaultVisible).toBe(false);
  });

  it("hides readouts no compound has a value for", () => {
    expect(by("Lowest shifting conc. (Main, ±2 °C)")).toMatchObject({
      empty: true,
      defaultVisible: false,
    });
    expect(by("ΔTm (Low)")).toMatchObject({ empty: true, defaultVisible: false });
    expect(by("Max ΔTm (Main)").empty).toBe(false);
  });

  it("always shows a readout the hit rule uses", () => {
    const rule: HitCriterion = { readout_name: "Tm (Main)", operator: "gt", value: 60 };
    const c = activityCatalog(THERMAL, HAS_DATA, [rule]);
    expect(c.find((x) => x.readout === "Tm (Main)")!.defaultVisible).toBe(true);
  });
});

describe("activityCatalog for a plain protocol", () => {
  it("shows plain readouts ungrouped by default", () => {
    const c = activityCatalog([plain("% Inhibition", "%")], [item({ "% Inhibition": 50 })], []);
    expect(c).toMatchObject([
      { readout: "% Inhibition", group: null, label: "% Inhibition (%)", defaultVisible: true },
    ]);
  });
});

describe("activityCatalog for a dose-response protocol", () => {
  it("shows the primary intercept, class and curve; secondaries on demand", () => {
    const dr = {
      name: "IC50",
      data_type: "dose_response",
      unit: "µM",
      best_direction: "low",
      intercepts: [
        { kind: "ic", level: 50, basis: "relative_percent", label: null },
        { kind: "ic", level: 90, basis: "relative_percent", label: null },
      ],
    } as unknown as ReadoutDefInfo;
    const c = activityCatalog([dr], [item({ IC50: 3 })], []);
    expect(c.map((x) => [x.kind, x.label, x.defaultVisible])).toEqual([
      ["intercept", "IC50 (µM)", true],
      ["intercept", "IC90 (µM)", false],
      ["class", "Class", true],
      ["curve", "Curve", true],
    ]);
    expect(new Set(c.map((x) => x.group))).toEqual(new Set(["IC50"]));
  });
});

describe("visibleColumnIds", () => {
  it("applies the user's choices over the defaults", () => {
    const catalog = activityCatalog(THERMAL, HAS_DATA, []);
    const tm = catalog.find((c) => c.readout === "Tm (Main)")!.colId;
    const max = catalog.find((c) => c.readout === "Max ΔTm (Main)")!.colId;
    const shown = visibleColumnIds(catalog, { shown: [tm], hidden: [max] });
    expect(shown.has(tm)).toBe(true);
    expect(shown.has(max)).toBe(false);
  });
});

describe("sorting", () => {
  it("magnitude sorts by size in either direction, missing last", () => {
    const cmp = compareForDirection("magnitude");
    const values = [1.4, null, -8.5, -0.9];
    // AG Grid passes isDescending and reverses the comparator's result.
    const desc = [...values].sort((a, b) => -cmp(a, b, undefined, undefined, true));
    expect(desc).toEqual([-8.5, 1.4, -0.9, null]);
    const asc = [...values].sort((a, b) => cmp(a, b, undefined, undefined, false));
    expect(asc).toEqual([-0.9, 1.4, -8.5, null]);
  });

  it("defaults to the hit rule's readout, else the first shown value, in its direction", () => {
    const catalog = activityCatalog(THERMAL, HAS_DATA, []);
    expect(defaultSortColumn(catalog, THERMAL, [])).toEqual({
      colId: catalog.find((c) => c.readout === "Max ΔTm (Main)")!.colId,
      sort: "desc",
    });
    const rule: HitCriterion = {
      readout_name: "Lowest shifting conc. (Main, ±2 °C)",
      operator: "lt",
      value: 10,
    };
    const withRule = activityCatalog(THERMAL, HAS_DATA, [rule]);
    expect(defaultSortColumn(withRule, THERMAL, [rule])).toEqual({
      colId: withRule.find((c) => c.readout === rule.readout_name)!.colId,
      sort: "asc",
    });
  });
});
