import { describe, expect, it } from "vitest";
import type { PanelPatch } from "../../store/workbench-store";
import type { Dataset } from "../../types";
import { crossProtocol, singleProtocol } from "../cross-protocol-fixture";
import { addMissingStrip } from "./missing-strip";
import { buildScatterBase } from "./scatter";
import { panel, pass } from "./test-fixtures";

/** Counter's pIC50 on X against Primary's on Y. */
const onCounter = (patch: PanelPatch = {}) =>
  panel("scatter", { x: "dr:y:p", y: "dr:x:p", ...patch });

function strip(ds: Dataset, p = onCounter(), mask = pass(ds.row_count)) {
  return addMissingStrip(buildScatterBase(ds, p, mask), ds, p, mask);
}

const onX2 = (fig: { data: Record<string, unknown>[] }) => fig.data.filter((t) => t.xaxis === "x2");

describe("addMissingStrip", () => {
  it("puts rows lacking X on a labeled strip left of the axis, selectable", () => {
    const { fig, stripped } = strip(crossProtocol);
    expect(stripped).toBe(2);
    const [t] = onX2(fig);
    expect(t.customdata).toEqual([1, 2]);
    expect(t.y).toEqual([6, 6.5]);
    expect((t.marker as { symbol: string }).symbol).toBe("line-ns-open");
    const x2 = fig.layout.xaxis2 as Record<string, unknown>;
    expect(x2.domain).toEqual([0, 0.08]);
    expect(x2.tickvals).toEqual([0, 1]);
    expect(x2.ticktext).toEqual(["Not tested (1)", "No value (1)"]);
    // The hover card names the protocol (not the tick): Plotly's own label is off.
    expect(t).toMatchObject({ hoverinfo: "none" });
    expect(t.text).toBeUndefined();
    // Jittered within each slot, the same on every build.
    const xs = t.x as number[];
    expect(Math.abs(xs[0])).toBeLessThanOrEqual(0.3);
    expect(Math.abs(xs[1] - 1)).toBeLessThanOrEqual(0.3);
    expect(strip(crossProtocol).fig.data).toEqual(fig.data);
    expect((fig.layout.xaxis as { domain: number[] }).domain).toEqual([0.11, 1]);
    expect(fig.layout.yaxis).toMatchObject({ anchor: "free", position: 0 });
    expect(fig.layout.shapes).toEqual([
      expect.objectContaining({ type: "rect", xref: "x2 domain", layer: "below" }),
    ]);
  });

  it("counts measured pairs and why the other rows have none", () => {
    expect(strip(crossProtocol).fig.note).toBe(
      "1 measured pair · 1 not tested in Counter · 1 no value",
    );
  });

  it("draws no strip when split, counting pairs in the footer only", () => {
    const split = onCounter({ appearance: { splitBy: "compound" } as PanelPatch["appearance"] });
    const { fig, stripped } = strip(crossProtocol, split);
    expect(stripped).toBe(0);
    // Facets take the further axes; no trace is the strip.
    expect(fig.data.some((t) => t.uid === "strip")).toBe(false);
    expect(fig.layout.shapes).toBeUndefined();
    expect(fig.note).toBe("1 measured pair · 1 not tested in Counter · 1 no value");
  });

  it("leaves a single-protocol scatter as it was", () => {
    const fig = buildScatterBase(singleProtocol, onCounter(), pass(3));
    expect(addMissingStrip(fig, singleProtocol, onCounter(), pass(3))).toEqual({
      fig,
      stripped: 0,
    });
  });

  it("puts every row on the strip when the protocols share no compounds", () => {
    const none: Dataset = {
      ...crossProtocol,
      values: {
        ...crossProtocol.values,
        "tested:B": ["Not tested", "Not tested", "Not tested"],
        "dr:y:p": [null, null, null],
      },
    };
    const { fig, stripped } = strip(none);
    expect(stripped).toBe(3);
    expect(fig.data.filter((t) => t.xaxis === "x")).toEqual([]);
    expect((fig.layout.xaxis2 as { ticktext: string[] }).ticktext).toEqual(["Not tested (3)"]);
    expect(fig.note).toBe("0 measured pairs · 3 not tested in Counter");
  });

  it("keeps the tick short however long the protocol's name", () => {
    const long: Dataset = {
      ...crossProtocol,
      protocols: [
        { protocol_id: "A", name: "Primary" },
        { protocol_id: "B", name: "Mtb_WCA_mc2-7000_Resazurin counter-screen, second site" },
      ],
    };
    const { fig } = strip(long);
    expect((fig.layout.xaxis2 as { ticktext: string[] }).ticktext).toEqual([
      "Not tested (1)",
      "No value (1)",
    ]);
  });

  it("puts rows with an X but no Y on a strip below the X axis", () => {
    const onPrimary = panel("scatter", { x: "dr:x:p", y: "dr:y:p" });
    const { fig, stripped } = strip(crossProtocol, onPrimary);
    expect(stripped).toBe(2);
    const t = fig.data.find((d) => d.yaxis === "y2") as Record<string, unknown>;
    expect(t).toMatchObject({ xaxis: "x", customdata: [1, 2], x: [6, 6.5] });
    expect(t).toMatchObject({ hoverinfo: "none" });
    const ys = t.y as number[];
    expect(Math.abs(ys[0])).toBeLessThanOrEqual(0.3);
    expect(Math.abs(ys[1] - 1)).toBeLessThanOrEqual(0.3);
    expect(fig.layout.yaxis2).toMatchObject({
      domain: [0, 0.08],
      tickvals: [0, 1],
      ticktext: ["Not tested (1)", "No value (1)"],
    });
    expect((fig.layout.yaxis as { domain: number[] }).domain).toEqual([0.11, 1]);
    // The X axis stands below the strip, which shares it.
    expect(fig.layout.xaxis).toMatchObject({ anchor: "free", position: 0 });
    expect(fig.layout.shapes).toEqual([
      expect.objectContaining({ type: "rect", yref: "y2 domain", layer: "below" }),
    ]);
  });
});
