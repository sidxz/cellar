import type {
  DoseResponseConfig,
  InterceptSpec,
  Protocol,
  ReadoutDefinition,
} from "@/features/screening-assay/types";
import { describe, expect, it } from "vitest";
import {
  CURVE_CLASS_OPTION_ID,
  POTENCY_UM_OPTION_ID,
  buildActivityWhereOptions,
  buildAnyProtocolWhereOptions,
  parseWhereOptionId,
  whereConditionOptionId,
} from "./activity-where-options";

const RD_DR = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa";
const RD_NUM = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb";
const RD_DR_TARGET = "cccccccc-cccc-cccc-cccc-cccccccccccc";
const RD_DR_COUNTER = "dddddddd-dddd-dddd-dddd-dddddddddddd";

function rd(over: Partial<ReadoutDefinition> & { id: string }): ReadoutDefinition {
  const { id, ...rest } = over;
  return {
    id,
    name: "Readout",
    description: null,
    data_type: "numeric",
    unit: null,
    aggregation: "mean",
    precision: null,
    normalizations: [],
    is_calculated: false,
    calculation_formula: null,
    display_order: 0,
    pick_list_values: null,
    dose_response_config: null,
    ...rest,
  } as ReadoutDefinition;
}

function proto(rds: ReadoutDefinition[]): Protocol {
  return { id: "p", name: "P", readout_definitions: rds } as unknown as Protocol;
}

function drConfig(curve_type: "ic50" | "ec50", intercepts: InterceptSpec[]): DoseResponseConfig {
  return {
    curve_type,
    y_readout_name: "raw",
    x_readout_name: null,
    intercepts,
    hill_slope_constraint: "unconstrained",
    activity_threshold: null,
    normalization_scope: "per_plate",
    top_constraint: null,
    bottom_constraint: null,
    top_constraint_min: null,
    top_constraint_max: null,
    bottom_constraint_min: null,
    bottom_constraint_max: null,
    hill_slope_min: null,
    hill_slope_max: null,
    outlier_sigma: null,
  } as DoseResponseConfig;
}

describe("buildActivityWhereOptions", () => {
  it("emits one option per intercept on a multi-intercept DR readout", () => {
    // EC50 (primary) + EC90 (secondary) — both must be filterable.
    const protocol = proto([
      rd({
        id: RD_DR,
        name: "Resazurin",
        data_type: "dose_response",
        dose_response_config: {
          curve_type: "ec50",
          x_readout_name: null,
          y_readout_name: "raw",
          intercepts: [
            { kind: "ec", level: 50, basis: "relative_percent" },
            { kind: "ec", level: 90, basis: "relative_percent" },
          ],
          hill_slope_constraint: "unconstrained",
          activity_threshold: null,
          normalization_scope: "per_plate",
          top_constraint: null,
          bottom_constraint: null,
          top_constraint_min: null,
          top_constraint_max: null,
          bottom_constraint_min: null,
          bottom_constraint_max: null,
          hill_slope_min: null,
          hill_slope_max: null,
          outlier_sigma: null,
        } as unknown as ReadoutDefinition["dose_response_config"],
      }),
    ]);

    const opts = buildActivityWhereOptions(protocol);
    // 2 intercepts + 1 curve_class option = 3 entries.
    expect(opts).toHaveLength(3);

    const dr = opts.filter((o) => o.group === "dose_response");
    // Readout name "Resazurin" differs from the primary intercept "EC50", so
    // both labels carry the rd prefix.
    expect(dr.map((o) => o.label)).toEqual(["Resazurin EC50", "Resazurin EC90"]);
    // Primary stays unkeyed so legacy saved searches round-trip unchanged.
    expect(dr[0].intercept_key).toBeNull();
    expect(dr[1].intercept_key).toEqual({ kind: "ec", level: 90 });
  });

  it("dedupes the rd-name prefix when it matches the primary intercept", () => {
    // The screenshot case: chemist names the readout "EC50" with intercepts
    // [EC50, EC90]. Labels should read as "EC50" / "EC90" — not
    // "EC50 EC50" / "EC50 EC90".
    const protocol = proto([
      rd({
        id: RD_DR,
        name: "EC50",
        data_type: "dose_response",
        dose_response_config: {
          curve_type: "ec50",
          intercepts: [
            { kind: "ec", level: 50, basis: "relative_percent" },
            { kind: "ec", level: 90, basis: "relative_percent" },
          ],
        } as unknown as ReadoutDefinition["dose_response_config"],
      }),
    ]);
    const opts = buildActivityWhereOptions(protocol);
    const dr = opts.filter((o) => o.group === "dose_response");
    expect(dr.map((o) => o.label)).toEqual(["EC50", "EC90"]);
  });

  it("emits one Curve Class entry when the protocol has at least one DR readout", () => {
    const protocol = proto([
      rd({
        id: RD_DR,
        data_type: "dose_response",
        dose_response_config: {
          curve_type: "ec50",
          intercepts: [{ kind: "ec", level: 50, basis: "relative_percent" }],
        } as unknown as ReadoutDefinition["dose_response_config"],
      }),
    ]);
    const opts = buildActivityWhereOptions(protocol);
    const cc = opts.filter((o) => o.group === "curve_class");
    expect(cc).toHaveLength(1);
    expect(cc[0].id).toBe(CURVE_CLASS_OPTION_ID);
    expect(cc[0].source).toBe("curve_class");
  });

  it("omits Curve Class when the protocol has no DR readouts", () => {
    const protocol = proto([rd({ id: RD_NUM, name: "OD600", data_type: "numeric" })]);
    const opts = buildActivityWhereOptions(protocol);
    expect(opts.filter((o) => o.group === "curve_class")).toHaveLength(0);
    expect(opts.filter((o) => o.group === "numeric_readout")).toHaveLength(1);
  });

  it("preserves multi-DR readouts as distinct groups", () => {
    // Two DR readout-defs (target + counter) — each surfaces its own
    // intercepts. Tests that we don't collapse on curve_type.
    const protocol = proto([
      rd({
        id: RD_DR_TARGET,
        name: "Target",
        data_type: "dose_response",
        dose_response_config: {
          curve_type: "ic50",
          intercepts: [{ kind: "ic", level: 50, basis: "relative_percent" }],
        } as unknown as ReadoutDefinition["dose_response_config"],
      }),
      rd({
        id: RD_DR_COUNTER,
        name: "Counter",
        data_type: "dose_response",
        dose_response_config: {
          curve_type: "ic50",
          intercepts: [{ kind: "ic", level: 50, basis: "relative_percent" }],
        } as unknown as ReadoutDefinition["dose_response_config"],
      }),
    ]);
    const opts = buildActivityWhereOptions(protocol);
    const dr = opts.filter((o) => o.group === "dose_response");
    expect(dr.map((o) => o.readout_definition_id)).toEqual([RD_DR_TARGET, RD_DR_COUNTER]);
  });
});

describe("parseWhereOptionId / whereConditionOptionId roundtrip", () => {
  it("preserves a primary DR option", () => {
    const id = `dr_curve:${RD_DR}`;
    const parsed = parseWhereOptionId(id);
    expect(parsed).toEqual({
      source: "dr_curve",
      readout_definition_id: RD_DR,
      intercept_key: null,
    });
    expect(
      whereConditionOptionId({
        source: "dr_curve",
        readout_definition_id: RD_DR,
        operator: "lt",
      }),
    ).toBe(id);
  });

  it("preserves a secondary intercept", () => {
    const id = `dr_curve:${RD_DR}:ec:90`;
    const parsed = parseWhereOptionId(id);
    expect(parsed).toEqual({
      source: "dr_curve",
      readout_definition_id: RD_DR,
      intercept_key: { kind: "ec", level: 90 },
    });
    expect(
      whereConditionOptionId({
        source: "dr_curve",
        readout_definition_id: RD_DR,
        operator: "lt",
        intercept_key: { kind: "ec", level: 90 },
      }),
    ).toBe(id);
  });

  it("preserves curve_class", () => {
    const parsed = parseWhereOptionId(CURVE_CLASS_OPTION_ID);
    expect(parsed?.source).toBe("curve_class");
    expect(
      whereConditionOptionId({
        source: "curve_class",
        readout_definition_id: "",
        operator: "eq",
        curve_classes: ["full"],
      }),
    ).toBe(CURVE_CLASS_OPTION_ID);
  });

  it("rejects unrecognised ids", () => {
    expect(parseWhereOptionId("garbage")).toBeNull();
    expect(parseWhereOptionId(`dr_curve:${RD_DR}:wat:50`)).toBeNull();
  });
});

describe("any-protocol derived catalog", () => {
  const P1 = "11111111-1111-1111-1111-111111111111";
  const P2 = "22222222-2222-2222-2222-222222222222";
  const P3 = "33333333-3333-3333-3333-333333333333";

  function protocolWith(id: string, rds: ReadoutDefinition[]): Protocol {
    return { ...proto([]), id, name: `P-${id.slice(0, 2)}`, readout_definitions: rds };
  }

  const ic50 = { kind: "ic" as const, level: 50, basis: "relative_percent" as const, label: null };
  const ic90 = { ...ic50, level: 90 };
  const ec50 = { kind: "ec" as const, level: 50, basis: "relative_percent" as const, label: null };

  const protocols = [
    protocolWith(P1, [
      rd({
        id: "a1",
        name: "IC50",
        data_type: "dose_response",
        unit: "uM",
        dose_response_config: drConfig("ic50", [ic50, ic90]),
      }),
      rd({ id: "a2", name: "% Inhibition", unit: "%" }),
    ]),
    protocolWith(P2, [
      rd({
        id: "b1",
        name: "IC50",
        data_type: "dose_response",
        unit: "nM",
        dose_response_config: drConfig("ic50", [ic50]),
      }),
      rd({ id: "b2", name: "%  inhibition ", unit: "%" }),
      rd({ id: "b3", name: "Scientist", data_type: "text" }),
    ]),
    protocolWith(P3, [
      rd({
        id: "c1",
        name: "EC50",
        data_type: "dose_response",
        unit: "uM",
        dose_response_config: drConfig("ec50", [ec50]),
      }),
      rd({ id: "c2", name: "% Inhibition", unit: null }),
    ]),
  ];

  it("groups DR intercepts by (kind, level) with protocol counts, µM unit", () => {
    const opts = buildAnyProtocolWhereOptions(protocols);
    const dr = opts.filter((o) => o.group === "dose_response");
    expect(dr.map((o) => [o.id, o.protocolCount])).toEqual([
      ["any:dr:ic:50", 2],
      ["any:dr:ec:50", 1],
      ["any:dr:ic:90", 1],
    ]);
    expect(dr[0].label).toBe("IC50 (µM) · 2 protocols");
    expect(dr[0].unit).toBe("µM");
    expect(dr[0].source).toBe("dr_curve");
    expect(dr[0].intercept_key).toEqual({ kind: "ic", level: 50 });
  });

  it("groups numeric readouts by normalized name + unit; text excluded", () => {
    const opts = buildAnyProtocolWhereOptions(protocols);
    const num = opts.filter((o) => o.group === "numeric_readout");
    expect(num.map((o) => [o.id, o.protocolCount])).toEqual([
      ["any:rd:% inhibition|%", 2],
      ["any:rd:% inhibition|", 1],
    ]);
    expect(num[0].label).toBe("% Inhibition (%) · 2 protocols");
    expect(num[1].label).toBe("% Inhibition · 1 protocol");
    expect(opts.some((o) => o.label.includes("Scientist"))).toBe(false);
  });

  it("always ends with Curve Class", () => {
    const opts = buildAnyProtocolWhereOptions(protocols);
    expect(opts[opts.length - 1].id).toBe(CURVE_CLASS_OPTION_ID);
    expect(buildAnyProtocolWhereOptions([]).map((o) => o.id)).toEqual([CURVE_CLASS_OPTION_ID]);
  });

  it("round-trips DR and readout ids through parse and back", () => {
    const dr = parseWhereOptionId("any:dr:ic:90");
    expect(dr).toEqual({
      source: "dr_curve",
      readout_definition_id: "",
      intercept_key: { kind: "ic", level: 90 },
    });
    expect(whereConditionOptionId({ ...dr!, operator: "lt", value: 1 }, true)).toBe("any:dr:ic:90");

    const rdc = parseWhereOptionId("any:rd:% inhibition|%");
    expect(rdc).toEqual({
      source: "readout_data",
      readout_definition_id: "",
      intercept_key: null,
      readout_name: "% inhibition",
      unit: "%",
    });
    expect(whereConditionOptionId({ ...rdc!, operator: "gt", value: 50 }, true)).toBe(
      "any:rd:% inhibition|%",
    );
    // per-protocol rows never resolve any:* ids
    expect(whereConditionOptionId({ ...rdc!, operator: "gt", value: 50 }, false)).toBe("");
  });

  it("a fresh any-protocol where-row seeds from the first catalog option, not the legacy potency shape", () => {
    // WhereList.add() on an any-protocol row seeds the new condition from
    // parseWhereOptionId(options[0].id) — proves that resolves to a real
    // dr_curve condition with an intercept_key, not the ambiguous
    // {source:"dr_curve", readout_definition_id:""} legacy shape.
    const opts = buildAnyProtocolWhereOptions(protocols);
    const seeded = parseWhereOptionId(opts[0].id);
    expect(seeded).toEqual({
      source: "dr_curve",
      readout_definition_id: "",
      intercept_key: { kind: "ic", level: 50 },
    });
  });

  it("legacy potency (dr_curve, no rd, no key) still resolves on any-protocol rows", () => {
    const cond = {
      source: "dr_curve" as const,
      readout_definition_id: "",
      operator: "lt" as const,
      value: 1,
      intercept_key: null,
    };
    expect(whereConditionOptionId(cond, true)).toBe(POTENCY_UM_OPTION_ID);
    expect(parseWhereOptionId(POTENCY_UM_OPTION_ID)).toEqual({
      source: "dr_curve",
      readout_definition_id: "",
      intercept_key: null,
    });
  });
});
