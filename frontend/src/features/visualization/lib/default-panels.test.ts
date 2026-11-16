import { describe, expect, it } from "vitest";
import type { Dataset, DatasetColumn } from "../types";
import { defaultPanels, panelDefaults } from "./default-panels";

const col = (key: string, kind: DatasetColumn["kind"]): DatasetColumn => ({
  key,
  label: key,
  kind,
  provenance: {},
});

const ds = (columns: DatasetColumn[]): Dataset => ({
  revision: "x",
  level: "wells",
  row_count: 0,
  row_ids: [],
  columns,
  values: {},
});

describe("defaultPanels", () => {
  it("scatters well order against the first numeric value column, split by plate", () => {
    const d = ds([
      col("plate", "category"),
      col("well_type", "category"),
      col("well_order", "number"),
      col("rd:pick:raw", "category"),
      col("rd:sig:raw", "number"),
      col("rd:sig:raw:q", "category"),
    ]);
    expect(defaultPanels(d)).toEqual([
      {
        type: "scatter",
        defaults: {
          x: "well_order",
          y: "rd:sig:raw",
          appearance: { splitBy: "plate", colorBy: "well_type", shapeBy: "well_type" },
        },
      },
    ]);
  });

  it("falls back to a count bar of well type when no numeric field exists", () => {
    const d = ds([
      col("well_type", "category"),
      col("well_order", "number"),
      col("rd:pick:raw", "category"),
    ]);
    expect(defaultPanels(d)).toEqual([
      { type: "bar", defaults: { agg: "count", category: "well_type" } },
    ]);
  });

  it("counts by the first category column when there is no well type", () => {
    const d = ds([col("compound", "category"), col("rd:pick:raw", "text")]);
    expect(defaultPanels(d)).toEqual([
      { type: "bar", defaults: { agg: "count", category: "compound" } },
    ]);
  });
});

describe("panelDefaults", () => {
  const d = ds([
    col("plate", "category"),
    col("well_type", "category"),
    col("well_order", "number"),
    col("rd:pick:raw", "category"),
    col("rd:sig:raw", "number"),
  ]);

  it("fills numeric fields with the first numeric value column and groups by well type", () => {
    expect(panelDefaults(d, "histogram")).toEqual({
      x: "rd:sig:raw",
      appearance: { colorBy: "well_type" },
    });
    expect(panelDefaults(d, "box")).toEqual({ y: "rd:sig:raw", category: "well_type" });
    expect(panelDefaults(d, "bar")).toEqual({ agg: "count", category: "well_type" });
    expect(panelDefaults(d, "scatter")).toEqual({
      x: "well_order",
      y: "rd:sig:raw",
      appearance: { colorBy: "well_type", shapeBy: "well_type" },
    });
  });

  it("falls back to the first category column and leaves histograms unstacked", () => {
    const plain = ds([col("compound", "category"), col("rd:sig:raw", "number")]);
    expect(panelDefaults(plain, "bar")).toEqual({ agg: "count", category: "compound" });
    expect(panelDefaults(plain, "histogram")).toEqual({ x: "rd:sig:raw", appearance: {} });
  });
});
