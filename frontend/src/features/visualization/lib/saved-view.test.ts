import { describe, expect, it } from "vitest";
import { makePanel } from "../store/workbench-store";
import type { Dataset } from "../types";
import { MAX_VIEW_CONFIG_BYTES, VIEW_CONFIG_VERSION, type ViewConfig } from "./config-schema";
import type { Filter } from "./filters";
import { buildViewConfig, configBytes, migrateViewConfig, resolveViewConfig } from "./saved-view";

const X = "rd:X:percent_inhibition";
const Y = "rd:Y:raw";
const UUID = /[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/i;

const ds: Dataset = {
  revision: "r",
  level: "wells",
  row_count: 2,
  row_ids: ["0b9c7a52-0c1e-4d43-9a65-2b0c8f7f1e11", "w2"],
  columns: [
    { key: "well_order", label: "Well order", kind: "number", provenance: {} },
    { key: "well_type", label: "Well type", kind: "category", provenance: {} },
    { key: "plate", label: "Plate", kind: "category", provenance: {} },
    { key: X, label: "Signal · % Inhibition", kind: "number", provenance: {} },
    { key: Y, label: "IC50 · NadD-counter", kind: "number", provenance: {} },
  ],
  values: {
    well_order: [1, 2],
    well_type: ["sample", "sample"],
    plate: ["P1", "P1"],
    [X]: [10, 20],
    [Y]: [1, 2],
  },
};

const rangeOn = (id: string, key: string): Filter => ({
  id,
  kind: "range",
  key,
  min: 1,
  max: null,
  includeMissing: false,
});

const scatter = makePanel("scatter", {
  x: "well_order",
  y: X,
  appearance: { colorBy: "well_type", splitBy: "plate", tooltip: [Y] },
});

describe("buildViewConfig", () => {
  const filters: Filter[] = [
    rangeOn("f1", Y),
    { id: "selection", kind: "rows", rowIds: [ds.row_ids[0]] },
  ];
  const cfg = buildViewConfig({ panels: [scatter], filters }, ds);

  it("keeps panels and saved filters, never the rows filter", () => {
    expect(cfg.config_version).toBe(VIEW_CONFIG_VERSION);
    expect(cfg.panels).toEqual([scatter]);
    expect(cfg.filters).toEqual([filters[0]]);
    expect(JSON.stringify(cfg)).not.toContain(ds.row_ids[0]);
  });

  it("labels every key the panels and filters reference", () => {
    expect(cfg.labels).toEqual({
      well_order: "Well order",
      [X]: "Signal · % Inhibition",
      well_type: "Well type",
      plate: "Plate",
      [Y]: "IC50 · NadD-counter",
    });
  });
});

describe("configBytes", () => {
  it("counts the UTF-8 JSON, so a 10k-value category filter is over the limit", () => {
    const values = Array.from({ length: 10_000 }, (_, i) => `compound-value-${i}`);
    const big = buildViewConfig(
      {
        panels: [],
        filters: [{ id: "c", kind: "category", key: "plate", values, includeMissing: true }],
      },
      ds,
    );
    expect(configBytes(big)).toBeGreaterThan(MAX_VIEW_CONFIG_BYTES);
    expect(configBytes({ config_version: 1, panels: [], filters: [], labels: { a: "é" } })).toBe(
      new TextEncoder().encode('{"config_version":1,"panels":[],"filters":[],"labels":{"a":"é"}}')
        .length,
    );
  });
});

describe("migrateViewConfig", () => {
  const v1: ViewConfig = buildViewConfig({ panels: [scatter], filters: [rangeOn("f1", Y)] }, ds);

  it("reads a current config unchanged", () => {
    expect(migrateViewConfig(v1)).toEqual({ ok: true, config: v1 });
  });

  it("refuses a newer config", () => {
    expect(migrateViewConfig({ ...v1, config_version: 2 })).toEqual({
      ok: false,
      reason: "This view was saved by a newer version of ChemCellar. Reload the page to open it.",
    });
  });

  it("refuses what it can't read", () => {
    const reason = "This view's settings can't be read.";
    expect(migrateViewConfig("garbage")).toEqual({ ok: false, reason });
    expect(migrateViewConfig({ ...v1, panels: "nope" })).toEqual({ ok: false, reason });
    expect(migrateViewConfig({ ...v1, config_version: 0 }, 1, {})).toEqual({ ok: false, reason });
  });

  it("applies each step from the stored version up", () => {
    const steps = {
      1: (c: ViewConfig) => ({
        ...c,
        config_version: 2,
        panels: c.panels.map((p) => ({ ...p, bins: 20 })),
      }),
    };
    const out = migrateViewConfig(v1, 2, steps);
    expect(out.ok && out.config.config_version).toBe(2);
    expect(out.ok && out.config.panels[0].bins).toBe(20);
  });
});

describe("resolveViewConfig", () => {
  it("drops what the dataset lacks, naming it by its saved label", () => {
    const cfg = buildViewConfig(
      { panels: [scatter], filters: [rangeOn("f1", Y), rangeOn("f2", X)] },
      ds,
    );
    const lacking: Dataset = { ...ds, columns: ds.columns.filter((c) => c.key !== Y) };
    const out = resolveViewConfig(cfg, lacking);
    expect(out.filters.map((f) => f.id)).toEqual(["f2"]);
    expect(out.missing).toContain("Filter: IC50 · NadD-counter");
    expect(out.missing).toContain("Plot 1: Tooltip (IC50 · NadD-counter)");
    expect(out.missing.some((m) => UUID.test(m))).toBe(false);
    expect(out.panels.map((p) => p.id)).toEqual([scatter.id]);
    expect(out.panels[0].appearance.tooltip).toEqual([]);
  });

  it("keeps everything when the dataset has every column", () => {
    const cfg = buildViewConfig({ panels: [scatter], filters: [rangeOn("f1", Y)] }, ds);
    expect(resolveViewConfig(cfg, ds)).toEqual({
      panels: cfg.panels,
      filters: cfg.filters,
      missing: [],
    });
  });
});
