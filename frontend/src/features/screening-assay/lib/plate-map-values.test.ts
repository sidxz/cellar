import { describe, expect, it } from "vitest";
import type { PlateData, PlateMapWell } from "../types";
import { buildPlateScale, compoundColorsForPlates } from "./plate-map-values";

const plate = (id: string, wells: Partial<PlateMapWell>[]) =>
  ({
    plate_id: id,
    wells: wells.map((well) => ({ well_type: "sample", ...well })),
  }) as PlateData;

describe("shared plate scales", () => {
  it("uses one run-wide range for plates with very different response distributions", () => {
    const first = plate("p1", [{ well_id: "a" }, { well_id: "b" }]);
    const second = plate("p2", [{ well_id: "c" }, { well_id: "d" }]);
    const values = new Map([
      ["a", 0],
      ["b", 10],
      ["c", 10],
      ["d", 100],
    ]);
    const shared = buildPlateScale({
      plates: [first, second],
      values,
      outliers: new Set(),
      kind: "linear",
    });
    expect(shared).toMatchObject({ low: 0, high: 100 });
    const firstOnly = buildPlateScale({
      plates: [first],
      values,
      outliers: new Set(),
      kind: "linear",
    });
    expect(firstOnly).toMatchObject({ low: 0, high: 10 });
  });

  it("pools individual control wells and excludes flagged controls from raw anchors", () => {
    const first = plate("p1", [
      { well_id: "pos1", well_type: "positive_control" },
      { well_id: "neg1", well_type: "negative_control" },
    ]);
    const second = plate("p2", [
      { well_id: "pos2", well_type: "positive_control" },
      { well_id: "pos3", well_type: "positive_control" },
      { well_id: "pos-bad", well_type: "positive_control" },
      { well_id: "neg2", well_type: "negative_control" },
    ]);
    const values = new Map([
      ["pos1", 10],
      ["pos2", 30],
      ["pos3", 30],
      ["pos-bad", 10000],
      ["neg1", 0],
      ["neg2", 5],
    ]);
    const scale = buildPlateScale({
      plates: [first, second],
      values,
      outliers: new Set(["pos-bad"]),
      kind: "linear",
    });
    expect(scale.posMean).toBeCloseTo(70 / 3);
    expect(scale.negMean).toBe(2.5);
    expect(scale.high).toBe(2.5);
    expect(values.get("pos-bad")).toBe(10000);
  });

  it.each([
    ["percent_inhibition", 0, 100],
    ["percent_activation", 0, 100],
    ["percent_control", 100, 0],
  ] as const)("keeps %s anchored to its biological endpoints", (normalization, none, full) => {
    const scale = buildPlateScale({
      plates: [plate("p1", [{ well_id: "a" }, { well_id: "b" }])],
      values: new Map([
        ["a", -35],
        ["b", 180],
      ]),
      outliers: new Set(),
      kind: "linear",
      normalization,
    });
    expect(scale.high).toBe(full);
    expect(scale.low).toBe(2 * none - full);
    expect(scale.marks?.map((mark) => mark.value)).toEqual([none, full]);
  });

  it("uses eligible run-wide wells for z-score scaling without discarding outlier values", () => {
    const values = new Map([
      ["a", 1],
      ["b", 3],
      ["excluded", 1000],
    ]);
    const scale = buildPlateScale({
      plates: [
        plate("p1", [{ well_id: "a" }]),
        plate("p2", [{ well_id: "b" }, { well_id: "excluded" }]),
      ],
      values,
      outliers: new Set(["excluded"]),
      kind: "zscore",
    });
    expect(scale.zMean).toBe(2);
    expect(scale.zStd).toBeCloseTo(Math.sqrt(2));
    expect(values.get("excluded")).toBe(1000);
  });

  it("keeps physical concentrations in range even when a response is flagged", () => {
    const scale = buildPlateScale({
      plates: [plate("p1", [{ well_id: "a" }]), plate("p2", [{ well_id: "excluded" }])],
      values: new Map([
        ["a", 0.1],
        ["excluded", 100],
      ]),
      outliers: new Set(["excluded"]),
      kind: "linear",
      concentration: true,
    });
    expect(scale).toMatchObject({ low: 0.1, high: 100 });
  });

  it("has a finite nonzero range for missing, invalid, or constant data", () => {
    const p = plate("p1", [{ well_id: "a" }, { well_id: "b" }]);
    for (const values of [
      new Map<string, number>(),
      new Map([
        ["a", Number.NaN],
        ["b", Number.POSITIVE_INFINITY],
      ]),
      new Map([
        ["a", 5],
        ["b", 5],
      ]),
    ]) {
      const scale = buildPlateScale({ plates: [p], values, outliers: new Set(), kind: "linear" });
      expect(Number.isFinite(scale.low)).toBe(true);
      expect(Number.isFinite(scale.high)).toBe(true);
      expect(scale.high).toBeGreaterThan(scale.low);
    }
  });
});

it("keeps compound identity colours consistent across plates and plate ordering", () => {
  const first = plate("p1", [{ molecule_id: "compound-b" }, { molecule_id: "compound-a" }]);
  const second = plate("p2", [{ molecule_id: "compound-a" }, { molecule_id: "compound-c" }]);
  const colors = compoundColorsForPlates([first, second]);
  expect(colors).toEqual(compoundColorsForPlates([second, first]));
  expect(new Set(colors.values()).size).toBe(3);
  expect(colors.get("compound-a")).toBeDefined();
});
