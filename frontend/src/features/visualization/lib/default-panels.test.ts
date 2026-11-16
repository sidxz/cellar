import { describe, expect, it } from "vitest";
import type { Dataset, DatasetColumn } from "../types";
import { crossProtocol, pColumn } from "./cross-protocol-fixture";
import { defaultPanels, panelDefaults, retypePanel } from "./default-panels";
import { panel, provenanceOf } from "./traces/test-fixtures";

const col = (key: string, kind: DatasetColumn["kind"]): DatasetColumn => ({
  key,
  label: key,
  kind,
  provenance: provenanceOf(key),
});

const ds = (columns: DatasetColumn[], values: Dataset["values"] = {}): Dataset => ({
  revision: "x",
  level: "wells",
  row_count: 0,
  row_ids: [],
  columns,
  values,
});

describe("defaultPanels", () => {
  it("scatters well order against the first numeric value column, split by plate", () => {
    const d = ds(
      [
        col("plate", "category"),
        col("well_type", "category"),
        col("well_order", "number"),
        col("rd:pick:raw", "category"),
        col("rd:sig:raw", "number"),
        col("rd:sig:raw:q", "category"),
      ],
      { well_order: [1, 2] },
    );
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

  it("opens summary-only runs (no well positions) on a histogram of the first value", () => {
    const d = ds(
      [
        col("well_type", "category"),
        col("well_order", "number"),
        col("rd:pick:raw", "category"),
        col("rd:ic50:raw", "number"),
      ],
      { well_order: [null, null] },
    );
    expect(defaultPanels(d)).toEqual([
      { type: "histogram", defaults: { x: "rd:ic50:raw", appearance: { colorBy: "well_type" } } },
    ]);
  });

  it("opens an aggregated level (no well columns) on a histogram of the first value", () => {
    const rd = (key: string, stat?: string): DatasetColumn => ({
      key,
      label: key,
      kind: stat === "qualifier" ? "category" : "number",
      provenance: { readout_definition_id: "a", aggregation: "mean", stat },
    });
    const d: Dataset = {
      ...ds([
        col("compound", "category"),
        rd("rd:a:raw:n", "n"),
        rd("rd:a:raw:q", "qualifier"),
        rd("rd:a:raw"),
        col("mw", "number"),
      ]),
      level: "compounds",
    };
    expect(defaultPanels(d)).toEqual([
      { type: "histogram", defaults: { x: "rd:a:raw", appearance: {} } },
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

describe("panelDefaults at aggregated levels", () => {
  const mean = (key: string, label: string, protocolId: string): DatasetColumn => ({
    ...pColumn(key, label, protocolId),
    provenance: { protocol_id: protocolId, readout_definition_id: "m", aggregation: "mean" },
  });

  it("scatters the primary protocol's potency against the compared protocol's matching one", () => {
    const d: Dataset = {
      ...crossProtocol,
      columns: [
        { key: "compound", label: "Compound", kind: "category", provenance: {} },
        mean("rd:m:pct", "Primary · % inhibition", "A"),
        pColumn("dr:x:p", "Primary · pIC50", "A"),
        pColumn("dr:z:p", "Counter · pEC50", "B"),
        pColumn("dr:y:p", "Counter · pIC50", "B"),
      ],
    };
    expect(panelDefaults(d, "scatter")).toMatchObject({ x: "dr:x:p", y: "dr:y:p" });
    // Without a matching potency, the compared protocol's first value still differs from X.
    const unmatched = {
      ...d,
      columns: [...d.columns.slice(0, 3), mean("rd:n:pct", "Counter · %", "B")],
    };
    expect(panelDefaults(unmatched, "scatter")).toMatchObject({ x: "dr:x:p", y: "rd:n:pct" });
  });

  it("never scatters a field against itself when another numeric field exists", () => {
    const d = {
      ...ds([col("rd:a:raw", "number"), col("rd:b:raw", "number")]),
      level: "compounds" as const,
    };
    const s = panelDefaults(d, "scatter");
    expect(s.x).not.toBe(s.y);
  });

  it("scatters two readouts, not a readout against its own p-value, unless only it exists", () => {
    const of = (key: string, readout: string, aggregation: string): DatasetColumn => ({
      key,
      label: key,
      kind: "number",
      provenance: { readout_definition_id: readout, aggregation },
    });
    const ic50 = of("dr:r1:fit", "r1", "fit");
    const pic50 = of("dr:r1:p", "r1", "p");
    const other = of("rd:r2:pct", "r2", "mean");
    const compounds = (columns: DatasetColumn[]) => ({
      ...ds(columns),
      level: "compounds" as const,
    });
    expect(panelDefaults(compounds([ic50, pic50, other]), "scatter")).toMatchObject({
      x: "rd:r2:pct",
      y: "dr:r1:fit",
    });
    expect(panelDefaults(compounds([ic50, pic50]), "scatter")).toMatchObject({
      x: "dr:r1:p",
      y: "dr:r1:fit",
    });
  });

  it("never groups a box or bar by the row's own identity, picking a real category or none", () => {
    const columns = [
      col("compound", "category"),
      col("batch", "category"),
      col("series", "category"),
      col("rd:a:raw", "number"),
    ];
    const compounds = { ...ds(columns), level: "compounds" as const };
    expect(panelDefaults(compounds, "box")).toEqual({ y: "rd:a:raw", category: "series" });
    expect(panelDefaults(compounds, "bar")).toEqual({ agg: "count", category: "series" });
    const batches = {
      ...ds([col("compound", "category"), col("batch", "category"), col("rd:a:raw", "number")]),
      level: "batches" as const,
    };
    expect(panelDefaults(batches, "box").category).toBeUndefined();
  });
});

describe("retypePanel", () => {
  const d = ds([
    col("plate", "category"),
    col("well_type", "category"),
    col("well_order", "number"),
    col("rd:a:raw", "number"),
    col("rd:b:raw", "number"),
  ]);
  const scatter = panel("scatter", { x: "rd:a:raw", y: "rd:b:raw", logX: true, logY: true });

  it("keeps the measured field and fills the group from the defaults", () => {
    expect(retypePanel(d, scatter, "box")).toMatchObject({
      type: "box",
      x: undefined,
      y: "rd:b:raw",
      logX: undefined,
      logY: true,
      category: "well_type",
    });
  });

  it("moves the measured field onto a histogram's X and back", () => {
    expect(retypePanel(d, scatter, "histogram")).toMatchObject({
      type: "histogram",
      x: "rd:b:raw",
      y: undefined,
      logY: undefined,
    });
    const hist = panel("histogram", { x: "rd:b:raw" });
    expect(retypePanel(d, hist, "scatter")).toMatchObject({
      x: "well_order",
      y: "rd:b:raw",
      appearance: { colorBy: "well_type", shapeBy: "well_type" },
    });
  });

  it("keeps a bar or box group and never overrides appearance already set", () => {
    const box = panel("box", {
      category: "plate",
      y: "rd:a:raw",
      appearance: { colorBy: "plate" },
    });
    expect(retypePanel(d, box, "bar")).toMatchObject({
      category: "plate",
      agg: "count",
      y: "rd:a:raw",
    });
    expect(retypePanel(d, box, "scatter").appearance).toEqual({ shapeBy: "well_type" });
  });
});
