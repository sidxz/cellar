import { describe, expect, it } from "vitest";
import type { Dataset, DatasetColumn } from "../types";
import {
  isCrossProtocol,
  isTestedInAll,
  missingReason,
  pairCounts,
  protocolName,
  selectivityKeys,
  testedCount,
  testedInAllFilters,
  testedKey,
} from "./cross-protocol";
import { newFilter } from "./filters";

const p = (key: string, label: string, protocolId: string): DatasetColumn => ({
  key,
  label,
  kind: "number",
  group: label.split(" · ")[0],
  provenance: {
    protocol_id: protocolId,
    readout_definition_id: key.split(":")[1],
    aggregation: "p",
  },
});

/** Protocol A ("Primary") owns the rows; B ("Counter") is compared: m1 tested in both with
 * values, m2 not tested in B, m3 tested in B without a value. */
const ds: Dataset = {
  revision: "r",
  level: "compounds",
  row_count: 3,
  row_ids: ["m1", "m2", "m3"],
  protocols: [
    { protocol_id: "A", name: "Primary" },
    { protocol_id: "B", name: "Counter" },
  ],
  columns: [
    { key: "compound", label: "Compound", kind: "text", provenance: {} },
    p("dr:x:p", "Primary · pIC50", "A"),
    {
      key: "tested:B",
      label: "Tested in Counter",
      kind: "category",
      group: "Counter",
      provenance: { protocol_id: "B" },
    },
    p("dr:y:p", "Counter · pIC50", "B"),
    {
      key: "sel:dr:x:p|dr:y:p",
      label: "Δ (Primary · pIC50) − (Counter · pIC50)",
      kind: "number",
      unit: "log units",
      group: "Selectivity",
      provenance: { aggregation: "selectivity" },
    },
  ],
  values: {
    compound: ["C1", "C2", "C3"],
    "dr:x:p": [7, 6, 6.5],
    "tested:B": ["Tested", "Not tested", "Tested"],
    "dr:y:p": [5, null, null],
    "sel:dr:x:p|dr:y:p": [2, null, null],
  },
};
const single: Dataset = { ...ds, protocols: [{ protocol_id: "A", name: "Primary" }] };
const all = new Uint8Array(3).fill(1);

describe("cross-protocol datasets", () => {
  it("is cross-protocol only with more than one protocol", () => {
    expect(isCrossProtocol(ds)).toBe(true);
    expect(isCrossProtocol(single)).toBe(false);
    expect(isCrossProtocol({ ...ds, protocols: undefined })).toBe(false);
  });

  it("names protocols, never by id", () => {
    expect(protocolName(ds, "B")).toBe("Counter");
    expect(protocolName(ds, "Z")).toBe("Unknown protocol");
  });

  it("splits a selectivity key into its two p columns", () => {
    expect(selectivityKeys("sel:dr:x:p|dr:y:p")).toEqual(["dr:x:p", "dr:y:p"]);
    expect(selectivityKeys("rd:x:raw")).toBeNull();
    expect(testedKey("B")).toBe("tested:B");
  });

  it("tells not tested apart from tested without a value", () => {
    expect(missingReason(ds, "dr:y:p", 0)).toBeNull();
    expect(missingReason(ds, "dr:y:p", 1)).toBe("Not tested in Counter");
    expect(missingReason(ds, "dr:y:p", 2)).toBe("No value");
    expect(missingReason(ds, "sel:dr:x:p|dr:y:p", 1)).toBe("Not tested in Counter");
    expect(missingReason(ds, "sel:dr:x:p|dr:y:p", 2)).toBe("No value");
    expect(missingReason(ds, "sel:dr:x:p|dr:y:p", 0)).toBeNull();
  });

  it("counts measured pairs and why the other passing rows have none", () => {
    expect(pairCounts(ds, "dr:x:p", "dr:y:p", all)).toEqual({
      pairs: 1,
      missing: [
        { reason: "Not tested in Counter", n: 1 },
        { reason: "No value", n: 1 },
      ],
    });
    expect(pairCounts(ds, "dr:y:p", "dr:x:p", Uint8Array.from([1, 0, 1]))).toEqual({
      pairs: 1,
      missing: [{ reason: "No value", n: 1 }],
    });
  });

  it("filters to compounds tested in every compared protocol", () => {
    const filters = testedInAllFilters(ds);
    expect(filters).toEqual([
      {
        id: "tested-all:B",
        kind: "category",
        key: "tested:B",
        values: ["Tested"],
        includeMissing: false,
      },
    ]);
    expect(testedInAllFilters(single)).toEqual([]);
    expect(isTestedInAll(filters, ds)).toBe(true);
    expect(isTestedInAll([], ds)).toBe(false);
    // The rail's own filter on the column, still holding both values, is not the toggle.
    const rail = newFilter(ds, "tested:B");
    expect(rail && isTestedInAll([rail], ds)).toBe(false);
    expect(isTestedInAll([], single)).toBe(false);
  });

  it("counts the compounds tested in a compared protocol", () => {
    expect(testedCount(ds, "B")).toBe(2);
    expect(testedCount(ds, "A")).toBe(0);
  });
});
