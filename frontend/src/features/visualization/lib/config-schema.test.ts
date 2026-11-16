import { describe, expect, it } from "vitest";
import { makePanel } from "../store/workbench-store";
import { filterSchema, panelSchema, savedFilterSchema, viewConfigSchema } from "./config-schema";

describe("config schemas", () => {
  it("a panel parses to itself", () => {
    const p = makePanel("scatter", {
      x: "well_order",
      y: "rd:X:raw",
      appearance: { colorBy: "well_type" },
    });
    expect(panelSchema.parse(p)).toEqual(p);
  });

  it("a panel with every overlay parses to itself", () => {
    const p = makePanel("scatter", {
      x: "well_order",
      y: "rd:X:raw",
      logY: true,
      bins: 20,
      overlays: {
        bands: true,
        drift: "trend",
        zPrime: true,
        refLine: 50,
        limits: { mode: "entered", lower: 10, upper: 90 },
        lipe: [3, 5],
        selectivity: [1],
      },
    });
    expect(panelSchema.parse(p)).toEqual(p);
  });

  it("only the live filter schema accepts a rows filter", () => {
    const rows = { id: "selection", kind: "rows", rowIds: ["w1"] };
    expect(savedFilterSchema.safeParse(rows).success).toBe(false);
    expect(filterSchema.safeParse(rows).success).toBe(true);
  });

  it("a saved substructure filter is its query: matched ids are never read back", () => {
    const query = { id: "sub-1", kind: "substructure", query: "c1ccccc1", queryKind: "smiles" };
    const sub = { ...query, moleculeIds: ["m1"] };
    expect(filterSchema.parse(sub)).toEqual(sub);
    expect(filterSchema.safeParse({ ...sub, queryKind: "inchi" }).success).toBe(false);
    expect(savedFilterSchema.parse(sub)).toEqual(query);
    // Opened from a view: not matched against this data yet.
    expect(filterSchema.parse(query)).toEqual(query);
  });

  it("a view config holds at most 4 panels", () => {
    const panels = Array.from({ length: 5 }, () => makePanel("histogram", { x: "a" }));
    const cfg = { config_version: 2, panels, filters: [], labels: {}, derived: [] };
    expect(viewConfigSchema.safeParse(cfg).success).toBe(false);
    expect(viewConfigSchema.safeParse({ ...cfg, panels: panels.slice(1) }).success).toBe(true);
  });
});
