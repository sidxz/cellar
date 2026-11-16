import { describe, expect, it } from "vitest";
import type { PanelPatch } from "../../store/workbench-store";
import type { Dataset, Level } from "../../types";
import { dataset, panel } from "../traces/test-fixtures";
import { overlayOptions } from "./options";

const Y = "rd:s:raw";
const P = "rd:a:raw:p";
const LOG = "Not available on a log axis";

const wells = dataset({
  well_order: [1, 2],
  well_column: [1, 2],
  dose: [0.1, 1],
  [Y]: [1, 2],
  plate: ["1", "2"],
  plate_id: ["a", "b"],
  well_type: ["sample", "negative_control"],
  run_date: ["2026-01-01", "2026-01-02"],
});
const scatter = (patch: PanelPatch = {}) => panel("scatter", { x: "well_order", y: Y, ...patch });

/** ``ds`` at ``level``, its ``:p`` column marked a p-potency as the server marks it. */
const at = (level: Level, ds: Dataset): Dataset => ({
  ...ds,
  level,
  columns: ds.columns.map((c) =>
    c.key === P ? { ...c, provenance: { ...c.provenance, stat: null, aggregation: "p" } } : c,
  ),
});

describe("overlayOptions", () => {
  it("offers the QC overlays on a wells scatter, Z′ only once split by plate", () => {
    expect(overlayOptions(wells, scatter())).toEqual({
      bands: true,
      driftBand: true,
      trend: true,
      zPrime: "Split by Plate to show stored Z′",
      refLine: true,
    });
    expect(overlayOptions(wells, scatter({ appearance: { splitBy: "plate" } })).zPrime).toBe(true);
  });

  it("disables data-coordinate overlays on a log axis", () => {
    const o = overlayOptions(wells, scatter({ logY: true, appearance: { splitBy: "plate" } }));
    expect(o).toMatchObject({ bands: LOG, driftBand: LOG, trend: LOG, refLine: LOG });
    expect(o.zPrime).toBe(true);
    expect(overlayOptions(wells, scatter({ logX: true })).bands).toBe(true);
  });

  it("draws drift bands along well order or column only, trends along any numeric X", () => {
    expect(overlayOptions(wells, scatter({ x: "dose" }))).toMatchObject({
      driftBand: "Drift bands need X = Well order or Column",
      trend: true,
    });
    expect(overlayOptions(wells, scatter({ x: "well_column" })).driftBand).toBe(true);
    expect(overlayOptions(wells, scatter({ x: "run_date" })).trend).toBe(
      "Trend lines need a numeric X",
    );
  });

  it("offers control limits at the runs level, along run date", () => {
    const runs = at("runs", dataset({ run_date: ["2026-01-01"], [Y]: [7.4], n: [3] }));
    expect(overlayOptions(runs, scatter({ x: "run_date" }))).toEqual({
      refLine: true,
      limits: true,
    });
    expect(overlayOptions(runs, scatter({ x: "n" })).limits).toBe("Set X to Run date");
  });

  it("offers LipE guides for a p-potency against logP", () => {
    const compounds = at(
      "compounds",
      dataset({ [P]: [7], [Y]: [3], logp: [2], molecular_weight: [300] }),
    );
    expect(overlayOptions(compounds, scatter({ x: "molecular_weight", y: P })).lipe).toBe(
      "Set X to logP",
    );
    expect(overlayOptions(compounds, scatter({ x: "logp", y: Y })).lipe).toBe(
      "Set Y to a p-potency",
    );
    expect(overlayOptions(compounds, scatter({ x: "logp", y: P })).lipe).toBe(true);
    expect(overlayOptions(compounds, scatter({ x: "logp", y: P, logX: true })).lipe).toBe(LOG);
    expect(overlayOptions(wells, scatter()).lipe).toBeUndefined();
  });

  it("offers nothing on a histogram and only a reference line on a box", () => {
    expect(overlayOptions(wells, panel("histogram", { x: Y }))).toEqual({});
    expect(overlayOptions(wells, panel("box", { y: Y, category: "well_type" }))).toEqual({
      refLine: true,
    });
  });
});
