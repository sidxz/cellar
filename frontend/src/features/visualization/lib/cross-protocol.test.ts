import { describe, expect, it } from "vitest";
import {
  isComparedValue,
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
import { crossProtocol, singleProtocol } from "./cross-protocol-fixture";
import { newFilter } from "./filters";

const ds = crossProtocol;
const single = singleProtocol;
const all = new Uint8Array(3).fill(1);

describe("cross-protocol datasets", () => {
  it("is cross-protocol only with more than one protocol", () => {
    expect(isCrossProtocol(ds)).toBe(true);
    expect(isCrossProtocol(single)).toBe(false);
    expect(isCrossProtocol({ ...ds, protocols: undefined })).toBe(false);
  });

  it("knows the values whose absence has a reason", () => {
    expect(isComparedValue(ds, "dr:y:p")).toBe(true);
    expect(isComparedValue(ds, "sel:dr:x:p|dr:y:p")).toBe(true);
    expect(isComparedValue(ds, "tested:B")).toBe(false);
    expect(isComparedValue(ds, "compound")).toBe(false);
    expect(isComparedValue(single, "dr:y:p")).toBe(false);
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
