import { describe, expect, it } from "vitest";
import { makePanel } from "../store/workbench-store";
import type { Dataset } from "../types";
import { MAX_VIEW_CONFIG_BYTES, VIEW_CONFIG_VERSION, type ViewConfig } from "./config-schema";
import type { DerivedSpec } from "./derived";
import type { Filter } from "./filters";
import {
  buildViewConfig,
  configBytes,
  migrateViewConfig,
  resolveViewConfig,
  sameDerived,
  sameSaved,
  tooLargeToSave,
} from "./saved-view";

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

  it("keeps a substructure filter's query, never its matched compounds", () => {
    const sub: Filter = {
      id: "sub-1",
      kind: "substructure",
      query: "c1ccccc1",
      queryKind: "smiles",
      moleculeIds: ["m-matched"],
    };
    const out = buildViewConfig({ panels: [], filters: [sub] }, ds);
    expect(out.filters).toEqual([
      { id: "sub-1", kind: "substructure", query: "c1ccccc1", queryKind: "smiles" },
    ]);
    expect(JSON.stringify(out)).not.toContain("m-matched");
    expect(out.labels).toEqual({});
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
    const small = { config_version: 2, panels: [], filters: [], labels: { a: "é" }, derived: [] };
    expect(configBytes(small)).toBe(
      new TextEncoder().encode(
        '{"config_version":2,"panels":[],"filters":[],"labels":{"a":"é"},"derived":[]}',
      ).length,
    );
  });
});

describe("tooLargeToSave", () => {
  it("names the size and the limit, and what to remove", () => {
    const values = Array.from({ length: 4_000 }, (_, i) => `compound-value-${i}`);
    const big = buildViewConfig(
      {
        panels: [],
        filters: [{ id: "c", kind: "category", key: "plate", values, includeMissing: true }],
      },
      ds,
    );
    const kb = Math.ceil(configBytes(big) / 1024);
    expect(kb).toBeGreaterThan(64);
    expect(tooLargeToSave(big)).toBe(
      `These settings are too large to save (${kb} KB of 64 KB). Remove some category filter values.`,
    );
    expect(tooLargeToSave(buildViewConfig({ panels: [scatter], filters: [] }, ds))).toBeNull();
  });
});

describe("sameSaved", () => {
  const sub: Filter = {
    id: "sub-1",
    kind: "substructure",
    query: "c1ccccc1",
    queryKind: "smiles",
  };

  it("ignores what a view never stores: the selection and a query's matches", () => {
    const saved = { panels: [scatter], filters: [sub] };
    const matched: Filter = { ...sub, moleculeIds: ["m1"] };
    const rows: Filter = { id: "selection", kind: "rows", rowIds: ["w2"] };
    expect(sameSaved(saved, { panels: [scatter], filters: [matched, rows] })).toBe(true);
  });

  it("sees a changed plot or filter", () => {
    const saved = { panels: [scatter], filters: [sub] };
    expect(sameSaved(saved, { panels: [{ ...scatter, logY: true }], filters: [sub] })).toBe(false);
    expect(sameSaved(saved, { panels: [scatter], filters: [] })).toBe(false);
  });
});

describe("migrateViewConfig", () => {
  const current: ViewConfig = buildViewConfig(
    { panels: [scatter], filters: [rangeOn("f1", Y)] },
    ds,
  );
  const { derived: _, ...v1 } = { ...current, config_version: 1 };

  it("reads a current config unchanged", () => {
    expect(migrateViewConfig(current)).toEqual({ ok: true, config: current });
  });

  it("opens a version-1 config with no chemistry columns", () => {
    expect(migrateViewConfig(v1)).toEqual({ ok: true, config: { ...current, derived: [] } });
  });

  it("refuses a newer config, for a reason of its own", () => {
    const newer = migrateViewConfig({ ...current, config_version: VIEW_CONFIG_VERSION + 1 });
    const unreadable = migrateViewConfig("garbage");
    expect(newer.ok).toBe(false);
    expect(!newer.ok && !unreadable.ok && newer.reason !== unreadable.reason).toBe(true);
  });

  it("refuses what it can't read", () => {
    expect(migrateViewConfig("garbage")).toMatchObject({ ok: false });
    expect(migrateViewConfig({ ...v1, panels: "nope" })).toMatchObject({ ok: false });
    expect(migrateViewConfig({ ...v1, config_version: 0 }, 1, {})).toMatchObject({ ok: false });
  });

  it("applies each step from the stored version up", () => {
    const steps = {
      1: (c: ViewConfig) => ({
        ...c,
        config_version: 2,
        panels: c.panels.map((p) => ({ ...p, bins: 20 })),
        derived: [],
      }),
    };
    const out = migrateViewConfig(v1, 2, steps);
    expect(out.ok && out.config.config_version).toBe(2);
    expect(out.ok && out.config.panels[0].bins).toBe(20);
  });
});

describe("a view's chemistry", () => {
  const rg1: DerivedSpec = {
    id: "rg1",
    kind: "rgroups",
    coreSmiles: "c1ccccc1[*:1]",
    name: "Core A",
  };
  const clusters: DerivedSpec = { id: "clusters", kind: "clusters", threshold: 0.4 };
  const matched: Filter = {
    id: "sub-1",
    kind: "substructure",
    query: "c1ccncc1",
    queryKind: "smarts",
    moleculeIds: ["m-matched"],
  };

  it("saves how each chemistry column set was made and a query without its matches", () => {
    const cfg = buildViewConfig({ panels: [scatter], filters: [matched] }, ds, [rg1, clusters]);
    const stored = JSON.parse(JSON.stringify(cfg));
    expect(migrateViewConfig(stored)).toEqual({ ok: true, config: cfg });
    expect(cfg.derived).toEqual([rg1, clusters]);
    expect(cfg.filters).toEqual([
      { id: "sub-1", kind: "substructure", query: "c1ccncc1", queryKind: "smarts" },
    ]);
    expect(JSON.stringify(stored)).not.toContain("m-matched");
  });

  it("tells chemistry apart by content, whatever the key order", () => {
    const reordered = JSON.parse(
      '{"name":"Core A","coreSmiles":"c1ccccc1[*:1]","kind":"rgroups","id":"rg1"}',
    );
    expect(sameDerived([rg1, clusters], [reordered, { ...clusters }])).toBe(true);
    expect(sameDerived([rg1], [rg1, clusters])).toBe(false);
    expect(sameDerived([rg1], [{ ...clusters, threshold: 0.5 }])).toBe(false);
    expect(sameDerived([], [])).toBe(true);
  });
});

describe("a saved view opened again", () => {
  it("keeps every plot's overlays", () => {
    const withOverlays = makePanel("scatter", {
      x: "well_order",
      y: X,
      overlays: {
        bands: true,
        drift: "band",
        zPrime: true,
        refLine: 50,
        limits: { mode: "entered", lower: 10, upper: 90 },
        lipe: [3, 5],
      },
    });
    const stored = JSON.parse(
      JSON.stringify(buildViewConfig({ panels: [withOverlays], filters: [] }, ds)),
    );
    const read = migrateViewConfig(stored);
    if (!read.ok) throw new Error(read.reason);
    expect(resolveViewConfig(read.config, ds).panels).toEqual([withOverlays]);
  });

  it("opens a substructure filter unmatched, without any compound ids", () => {
    const sub: Filter = {
      id: "sub-1",
      kind: "substructure",
      query: "c1ccccc1",
      queryKind: "smiles",
      moleculeIds: ["m1"],
    };
    const stored = JSON.parse(JSON.stringify(buildViewConfig({ panels: [], filters: [sub] }, ds)));
    const read = migrateViewConfig(stored);
    if (!read.ok) throw new Error(read.reason);
    expect(resolveViewConfig(read.config, ds).filters).toEqual([
      { id: "sub-1", kind: "substructure", query: "c1ccccc1", queryKind: "smiles" },
    ]);
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
