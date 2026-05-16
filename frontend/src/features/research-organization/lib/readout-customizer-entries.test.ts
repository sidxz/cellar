import { describe, expect, it } from "vitest";
import type {
  Protocol,
  ReadoutDefinition,
} from "@/features/screening-assay/types";
import {
  buildReadoutCustomizerEntries,
  replaceProtocolEntries,
} from "./readout-customizer-entries";

const PROTO_ID = "11111111-1111-1111-1111-111111111111";
const RD_DR = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa";
const RD_NUM = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb";

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
  return {
    id: PROTO_ID,
    name: "P",
    readout_definitions: rds,
  } as unknown as Protocol;
}

describe("buildReadoutCustomizerEntries", () => {
  it("emits one entry per intercept for a multi-intercept DR readout", () => {
    // The screenshot case: rd named "EC50" with intercepts [EC50, EC90].
    // Primary keys on the parent `drc:<rd>` (so it lines up with columns
    // produced by the filter / default-columns paths); secondaries use the
    // narrowed 4-segment token so per-intercept toggles work.
    const protocol = proto([
      rd({
        id: RD_DR,
        name: "EC50",
        unit: "uM",
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
    const entries = buildReadoutCustomizerEntries(protocol, PROTO_ID);
    // Both intercepts now use narrowed 4-segment keys (primary used to share
    // the parent `drc:<rd>` shape; narrowing means `set.has(entryKey)`
    // reflects per-intercept visibility uniformly).
    expect(entries).toEqual([
      { key: `drc:${RD_DR}:ec:50`, label: "EC50 (uM)" },
      { key: `drc:${RD_DR}:ec:90`, label: "EC90 (uM)" },
    ]);
  });

  it("keeps the rd-name prefix when it differs from the primary intercept", () => {
    const protocol = proto([
      rd({
        id: RD_DR,
        name: "Resazurin",
        unit: "uM",
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
    const entries = buildReadoutCustomizerEntries(protocol, PROTO_ID);
    expect(entries.map((e) => e.label)).toEqual([
      "Resazurin EC50 (uM)",
      "Resazurin EC90 (uM)",
    ]);
  });

  it("emits a single entry for a numeric readout", () => {
    const protocol = proto([
      rd({ id: RD_NUM, name: "OD600", unit: null, data_type: "numeric" }),
    ]);
    const entries = buildReadoutCustomizerEntries(protocol, PROTO_ID);
    expect(entries).toEqual([{ key: `rd:${PROTO_ID}:${RD_NUM}`, label: "OD600" }]);
  });

  it("falls back to a single parent entry on a DR readout with no intercepts", () => {
    const protocol = proto([
      rd({
        id: RD_DR,
        name: "Legacy",
        data_type: "dose_response",
        dose_response_config: {
          curve_type: "ic50",
          intercepts: [],
        } as unknown as ReadoutDefinition["dose_response_config"],
      }),
    ]);
    const entries = buildReadoutCustomizerEntries(protocol, PROTO_ID);
    expect(entries).toEqual([{ key: `drc:${RD_DR}`, label: "Legacy" }]);
  });

  it("returns [] when the protocol hasn't loaded yet", () => {
    expect(buildReadoutCustomizerEntries(undefined, PROTO_ID)).toEqual([]);
  });
});

describe("replaceProtocolEntries", () => {
  const A = "drc:rd-a";
  const B = "drc:rd-b";
  const B_EC90 = "drc:rd-b:ec:90";
  const C = "rd:proto-c:rd-c";

  it("preserves tokens outside the owned set", () => {
    // Customizer toggles a B-protocol entry off; A and C (other protocols)
    // must stay in their original positions.
    const next = replaceProtocolEntries([A, B, C], new Set([B, B_EC90]), []);
    expect(next).toEqual([A, C]);
  });

  it("appends new tokens that weren't in the previous list", () => {
    // Toggling EC90 ON adds B_EC90; the existing B (primary) stays put.
    const next = replaceProtocolEntries([A, B, C], new Set([B, B_EC90]), [B, B_EC90]);
    expect(next).toEqual([A, B, C, B_EC90]);
  });

  it("retains owned tokens that are in the new selection", () => {
    // Toggling B off but keeping B_EC90 — B should be removed, B_EC90 kept
    // / added (since it was already in current).
    const next = replaceProtocolEntries([A, B, B_EC90], new Set([B, B_EC90]), [B_EC90]);
    expect(next).toEqual([A, B_EC90]);
  });

  it("empties the owned set when nextOwned is []", () => {
    expect(
      replaceProtocolEntries([A, B, B_EC90, C], new Set([B, B_EC90]), []),
    ).toEqual([A, C]);
  });
});
