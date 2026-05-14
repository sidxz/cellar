import { describe, expect, it } from "vitest";
import type {
  Protocol,
  ReadoutDefinition,
} from "@/features/screening-assay/types";
import { resolveColumns, uniqueProtocolIds } from "./protocol-column-id";

const PROTO_A = "11111111-1111-1111-1111-111111111111";
const PROTO_B = "22222222-2222-2222-2222-222222222222";
const RD_A_DR = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa";
const RD_A_RAW = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb";
const RD_B_DR = "cccccccc-cccc-cccc-cccc-cccccccccccc";

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

function proto(id: string, rds: ReadoutDefinition[]): Protocol {
  return { id, name: "P", readout_definitions: rds } as unknown as Protocol;
}

const PROTOCOLS: Protocol[] = [
  proto(PROTO_A, [rd({ id: RD_A_DR, data_type: "dose_response" }), rd({ id: RD_A_RAW })]),
  proto(PROTO_B, [rd({ id: RD_B_DR, data_type: "dose_response" })]),
];

describe("uniqueProtocolIds", () => {
  it("derives proto IDs from drc:<rd_id> via the reverse readout-def index", () => {
    // Pre-033 the search drawer parsed parts[1] of `drc:<proto>:<curve>`
    // as a proto_id. After 033 the token is `drc:<rd_id>` — parts[1] is
    // a readout-def UUID, NOT a proto_id. Without this index the detail
    // sheet's "Selected Protocols" section silently goes empty whenever
    // every visible column is a DR column.
    const colIds = [`drc:${RD_A_DR}`, `drc:${RD_B_DR}`];
    expect(uniqueProtocolIds(colIds, PROTOCOLS).sort()).toEqual([PROTO_A, PROTO_B].sort());
  });

  it("dedupes when multiple columns reference the same protocol", () => {
    const colIds = [`drc:${RD_A_DR}`, `rd:${PROTO_A}:${RD_A_RAW}`];
    expect(uniqueProtocolIds(colIds, PROTOCOLS)).toEqual([PROTO_A]);
  });

  it("ignores tokens whose readout-def isn't owned by any known protocol", () => {
    expect(uniqueProtocolIds(["drc:not-a-real-rd"], PROTOCOLS)).toEqual([]);
  });

  it("handles mixed prefixes and segment counts", () => {
    const colIds = [
      `drc:${RD_A_DR}`,
      `rd:${PROTO_B}:${RD_B_DR}:percent_inhibition`,
      `rd:${RD_A_RAW}`,
    ];
    expect(uniqueProtocolIds(colIds, PROTOCOLS).sort()).toEqual([PROTO_A, PROTO_B].sort());
  });
});

describe("resolveColumns (shared)", () => {
  it("preserves token order while joining each colId to its proto", () => {
    const colIds = [`drc:${RD_A_DR}`, `rd:${PROTO_B}:${RD_B_DR}`];
    expect(resolveColumns(colIds, PROTOCOLS)).toEqual([
      { colId: `drc:${RD_A_DR}`, prefix: "drc", protocolId: PROTO_A, readoutDefId: RD_A_DR },
      { colId: `rd:${PROTO_B}:${RD_B_DR}`, prefix: "rd", protocolId: PROTO_B, readoutDefId: RD_B_DR },
    ]);
  });
});
