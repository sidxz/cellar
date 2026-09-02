import type { Protocol, ReadoutDefinition } from "@/features/screening-assay/types";
import { describe, expect, it } from "vitest";
import {
  CURVE_CLASS_OPTION_ID,
  buildActivityWhereOptions,
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

describe("any-protocol options", () => {
  it("offers only potency (µM) and curve class", async () => {
    const { buildAnyProtocolWhereOptions, POTENCY_UM_OPTION_ID } = await import(
      "./activity-where-options"
    );
    const opts = buildAnyProtocolWhereOptions();
    expect(opts.map((o) => o.id)).toEqual([POTENCY_UM_OPTION_ID, CURVE_CLASS_OPTION_ID]);
    expect(opts[0].unit).toBe("µM");
    expect(opts[0].source).toBe("dr_curve");
    expect(opts[0].readout_definition_id).toBe("");
  });

  it("round-trips the potency option through parse and back", async () => {
    const { POTENCY_UM_OPTION_ID } = await import("./activity-where-options");
    const seed = parseWhereOptionId(POTENCY_UM_OPTION_ID);
    expect(seed).toEqual({ source: "dr_curve", readout_definition_id: "", intercept_key: null });
    const cond = { ...seed!, operator: "lt" as const, value: 1 };
    expect(whereConditionOptionId(cond, true)).toBe(POTENCY_UM_OPTION_ID);
    // On a per-protocol row the same shape is just an unfilled fresh row.
    expect(whereConditionOptionId(cond, false)).toBe("");
  });
});
