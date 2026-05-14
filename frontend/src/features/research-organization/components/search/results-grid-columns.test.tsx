import { describe, expect, it } from "vitest";
import type {
  DoseResponseConfig,
  InterceptSpec,
  Protocol,
  ReadoutDefinition,
} from "@/features/screening-assay/types";
import { buildDrcColumns, resolveColumns } from "./results-grid";

const PROTO_ID = "11111111-1111-1111-1111-111111111111";
const RD_DR_ID = "22222222-2222-2222-2222-222222222222";
const RD_RAW_ID = "33333333-3333-3333-3333-333333333333";

function spec(over: Partial<InterceptSpec> = {}): InterceptSpec {
  return {
    kind: "ec",
    level: 50,
    basis: "relative_percent",
    label: null,
    ...over,
  };
}

function drConfig(intercepts: InterceptSpec[]): DoseResponseConfig {
  return {
    curve_type: "ec50",
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
  };
}

function rd(
  over: Partial<ReadoutDefinition> & { id: string },
): ReadoutDefinition {
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
  return {
    id: PROTO_ID,
    name: "Mtb_WCA",
    readout_definitions: rds,
  } as unknown as Protocol;
}

describe("resolveColumns", () => {
  it("maps drc:<rd_id> back to the owning protocol", () => {
    const p = proto([
      rd({
        id: RD_DR_ID,
        data_type: "dose_response",
        dose_response_config: drConfig([
          spec({ level: 50 }),
          spec({ level: 90, label: "EC90" }),
        ]),
      }),
    ]);
    const resolved = resolveColumns([`drc:${RD_DR_ID}`], [p]);
    expect(resolved).toHaveLength(1);
    expect(resolved[0]).toMatchObject({
      colId: `drc:${RD_DR_ID}`,
      prefix: "drc",
      protocolId: PROTO_ID,
      readoutDefId: RD_DR_ID,
    });
  });

  it("uses parts[1] as protocol_id for 3-segment rd: colIds", () => {
    const p = proto([rd({ id: RD_RAW_ID })]);
    const resolved = resolveColumns([`rd:${PROTO_ID}:${RD_RAW_ID}`], [p]);
    expect(resolved).toHaveLength(1);
    expect(resolved[0]).toMatchObject({
      prefix: "rd",
      protocolId: PROTO_ID,
      readoutDefId: RD_RAW_ID,
    });
  });

  it("supports 4-segment rd:<proto>:<rd>:<norm> colIds", () => {
    const p = proto([rd({ id: RD_RAW_ID })]);
    const resolved = resolveColumns(
      [`rd:${PROTO_ID}:${RD_RAW_ID}:percent_inhibition`],
      [p],
    );
    expect(resolved).toHaveLength(1);
    expect(resolved[0].protocolId).toBe(PROTO_ID);
    expect(resolved[0].readoutDefId).toBe(RD_RAW_ID);
  });

  it("falls back to readout-def reverse index for legacy 2-segment rd: colIds", () => {
    const p = proto([rd({ id: RD_RAW_ID })]);
    const resolved = resolveColumns([`rd:${RD_RAW_ID}`], [p]);
    expect(resolved).toHaveLength(1);
    expect(resolved[0].protocolId).toBe(PROTO_ID);
  });

  it("drops colIds with no resolvable protocol", () => {
    expect(resolveColumns(["drc:not-a-real-rd"], [proto([])])).toHaveLength(0);
    expect(resolveColumns(["pro:foo:bar"], [proto([])])).toHaveLength(0);
  });
});

describe("buildDrcColumns", () => {
  it("emits one column per protocol intercept plus a Plot column", () => {
    const dr = rd({
      id: RD_DR_ID,
      data_type: "dose_response",
      dose_response_config: drConfig([
        spec({ level: 50 }),
        spec({ level: 90, label: "EC90" }),
      ]),
    });
    const cols = buildDrcColumns(`drc:${RD_DR_ID}`, proto([dr]), RD_DR_ID);
    expect(cols).toHaveLength(3);
    expect(cols[0].headerName).toBe("EC50");
    expect(cols[1].headerName).toBe("EC90");
    expect(cols[2].headerName).toBe("Plot");
    expect(cols[0].colId).toBe(`drc:${RD_DR_ID}:ec:50`);
    expect(cols[1].colId).toBe(`drc:${RD_DR_ID}:ec:90`);
    expect(cols[2].colId).toBe(`drc:${RD_DR_ID}:plot`);
  });

  it("falls back to a single anonymous value column when no intercepts declared", () => {
    const dr = rd({
      id: RD_DR_ID,
      name: "Resazurin",
      data_type: "dose_response",
      dose_response_config: null,
    });
    const cols = buildDrcColumns(`drc:${RD_DR_ID}`, proto([dr]), RD_DR_ID);
    expect(cols).toHaveLength(2);
    expect(cols[0].headerName).toBe("Resazurin");
    expect(cols[0].colId).toBe(`drc:${RD_DR_ID}:value`);
    expect(cols[1].headerName).toBe("Plot");
  });
});
