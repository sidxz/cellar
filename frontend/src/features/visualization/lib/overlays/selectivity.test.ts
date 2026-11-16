import { describe, expect, it } from "vitest";
import type { OverlayConfig, PanelPatch } from "../../store/workbench-store";
import type { Dataset } from "../../types";
import { pColumn } from "../cross-protocol-fixture";
import { buildScatterBase } from "../traces/scatter";
import { panel, pass } from "../traces/test-fixtures";
import { buildOverlays } from "./build";
import { overlayOptions } from "./options";

type Mark = Record<string, unknown>;

/** Primary (A) owns two p-potencies, Counter (B) one; four measured pairs and a compound
 * not tested in Counter. */
const ds: Dataset = {
  revision: "r",
  level: "compounds",
  row_count: 5,
  row_ids: ["m1", "m2", "m3", "m4", "m5"],
  protocols: [
    { protocol_id: "A", name: "Primary" },
    { protocol_id: "B", name: "Counter" },
  ],
  columns: [
    pColumn("dr:a:p", "Primary · pIC50", "A"),
    pColumn("dr:a2:p", "Primary · pEC50", "A"),
    pColumn("dr:b:p", "Counter · pIC50", "B"),
    { key: "logp", label: "logP", kind: "number", provenance: {} },
  ],
  values: {
    "dr:a:p": [7, 6, 6, 9, 8],
    "dr:a2:p": [1, 2, 3, 4, 5],
    "dr:b:p": [5, 6, 8, 7, null],
    logp: [1, 2, 3, 4, 5],
  },
};
const single: Dataset = { ...ds, protocols: [{ protocol_id: "A", name: "Primary" }] };

/** Counter on X, Primary on Y. */
const scatter = (patch: PanelPatch = {}) =>
  panel("scatter", { x: "dr:b:p", y: "dr:a:p", ...patch });

function draw(overlays: OverlayConfig, patch: PanelPatch = {}) {
  const p = scatter({ overlays, ...patch });
  const mask = pass(ds.row_count);
  return buildOverlays(ds, p, mask, buildScatterBase(ds, p, mask).facets ?? []);
}

describe("selectivity guides", () => {
  it("are offered for a p-potency of each protocol, only when protocols are compared", () => {
    expect(overlayOptions(ds, scatter()).selectivity).toBe(true);
    expect(overlayOptions(ds, scatter({ x: "dr:a2:p" })).selectivity).toBe(
      "Plot a p-potency from each protocol on X and Y",
    );
    expect(overlayOptions(ds, scatter({ x: "logp" })).selectivity).toBe(
      "Plot a p-potency from each protocol on X and Y",
    );
    expect(overlayOptions(ds, scatter({ logX: true })).selectivity).toBe(
      "Not available on a log axis",
    );
    expect(overlayOptions(ds, scatter({ x: undefined })).selectivity).toBe(
      "Plot a p-potency from each protocol on X and Y",
    );
    expect(overlayOptions(single, scatter())).not.toHaveProperty("selectivity");
  });

  it("draw parity and each fold both ways, saying for which protocol, inside the pairs", () => {
    const { shapes, annotations, notes } = draw({ selectivity: [10] });
    expect(shapes.map((s) => [s.x0, s.y0, s.x1, s.y1])).toEqual([
      [6, 6, 8, 8],
      [5, 6, 8, 9],
      [7, 6, 8, 7],
    ]);
    for (const s of shapes) {
      expect(s).toMatchObject({ type: "line", xref: "x", yref: "y", name: "Selectivity guides" });
      // Inside the measured pairs' box: X 5–8, Y 6–9.
      for (const x of [s.x0, s.x1] as number[]) expect(x >= 5 && x <= 8).toBe(true);
      for (const y of [s.y0, s.y1] as number[]) expect(y >= 6 && y <= 9).toBe(true);
    }
    expect(shapes.map((s) => s.showlegend)).toEqual([true, false, false]);
    expect(annotations.map((a: Mark) => a.text)).toEqual([
      "1×",
      "≥10× selective for Primary",
      "≥10× selective for Counter",
    ]);
    expect(notes).toEqual([]);
  });

  it("says when a fold's guides miss the measured pairs, and leaves folds of 1 or less out", () => {
    const { shapes, notes } = draw({ selectivity: [100000, 1, 0.5] });
    expect(shapes).toHaveLength(1);
    expect(notes).toEqual([
      "Selectivity fold 1 left out: folds start above 1",
      "Selectivity fold 0.5 left out: folds start above 1",
      "100000× guides lie outside the measured pairs",
    ]);
  });

  it("draws nothing for a pair of the same protocol", () => {
    expect(draw({ selectivity: [10] }, { x: "dr:a2:p" }).shapes).toEqual([]);
  });
});
