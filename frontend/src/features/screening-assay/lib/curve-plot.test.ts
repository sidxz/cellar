import { describe, expect, it } from "vitest";

import { CHART_CANVAS, MEASURED_CURVE_COLORS } from "@/shared/lib/chart-colors";
import type { RunCurves } from "../types";
import { buildCurveFigure, focusIdFromHover, reportedColumns, tableRows } from "./curve-plot";

function position(id: string, column: number, wellType: string, label: string | null) {
  return {
    well_id: id,
    position: `A${column}`,
    row: "A",
    column,
    well_type: wellType,
    batch_id: null,
    batch_number: id === "w2" ? "B-001" : null,
    molecule_id: null,
    molecule_name: id === "w2" ? "ABC-0000001" : null,
    synonyms: [],
    smiles: null,
    dose: id === "w2" ? 50 : null,
    position_label: `Position ${column}`,
    label,
    note: id === "w3" ? "bubble" : null,
  };
}

const curves: RunCurves = {
  run_id: "r1",
  dose_unit: "uM",
  holder: { kind: "cassette", rows: 1, columns: 3, label: "Holder of 3" },
  positions: [
    position("w1", 1, "reference", "Protein alone"),
    position("w2", 2, "sample", "ABC-0000001"),
    position("w3", 3, "sample", null),
  ],
  channels: [{ key: "a", label: "Signal A", x_unit: "°C", y_unit: "u" }],
  channel: "a",
  curves: [
    {
      well_id: "w1",
      x: [20, 21, 22, 23],
      y: [1, 2, 3, 4],
      reported: [
        { kind: "k1", ordinal: 1, label: "Point 1", value: 21.5, unit: "°C" },
        { kind: "k1", ordinal: 2, label: "Point 2", value: 22.5, unit: "°C" },
        { kind: "k2", ordinal: 1, label: "Share", value: 40, unit: "%" },
      ],
    },
    {
      well_id: "w2",
      x: [20, 21],
      y: [5, 6],
      reported: [{ kind: "k1", ordinal: 1, label: "Point 1", value: 20.7, unit: "°C" }],
    },
    { well_id: "w3", x: [20, 21, 22], y: [7, 8, 9], reported: [] },
  ],
  view: "measured",
  window: null,
};

const dark = MEASURED_CURVE_COLORS.dark;
const light = MEASURED_CURVE_COLORS.light;

const base = {
  data: curves,
  selected: new Set(["w1", "w3"]),
  showReported: false,
  canvas: "screen" as const,
  colourMode: "highlight" as const,
  slots: new Map<string, number>(),
  focusedId: null,
  palette: "dark" as const,
};

type Trace = { x: number[]; line: { color: string; width: number }; opacity: number; name: string };

describe("buildCurveFigure", () => {
  it("draws one unchanged trace per selected position with a curve", () => {
    const { data } = buildCurveFigure(base) as unknown as { data: Trace[] };
    expect(data).toHaveLength(2);
    expect(data[0].x).toEqual(curves.curves[0].x);
    expect(data[0].name).toBe("Position 1 · Protein alone");
    expect(data[1].name).toBe("Position 3");
  });

  it("draws reference positions in the reference colour and the rest in neutral", () => {
    const { data } = buildCurveFigure(base) as unknown as { data: Trace[] };
    expect(data[0].line.color).toBe(dark.reference);
    expect(data[0].line.width).toBeGreaterThan(data[1].line.width);
    expect(data[1].line.color).toBe(dark.neutral);
  });

  it("draws the focused curve in the focus colour and dims the others", () => {
    const { data } = buildCurveFigure({ ...base, focusedId: "w3" }) as unknown as {
      data: Trace[];
    };
    expect(data[1].line.color).toBe(dark.focus);
    expect(data[1].opacity).toBe(1);
    expect(data[0].opacity).toBe(0.35);
  });

  it("uses each position's slot colour in distinct mode", () => {
    const { data } = buildCurveFigure({
      ...base,
      colourMode: "distinct",
      slots: new Map([
        ["w1", 4],
        ["w3", 1],
      ]),
    }) as unknown as { data: Trace[] };
    expect(data[0].line.color).toBe(dark.series[4]);
    expect(data[1].line.color).toBe(dark.series[1]);
  });

  it("falls back to highlight colours in distinct mode when no slots were assigned", () => {
    const { data } = buildCurveFigure({ ...base, colourMode: "distinct" }) as unknown as {
      data: Trace[];
    };
    expect(data[0].line.color).toBe(dark.reference);
  });

  it("draws reported values as vertical lines only when their unit is the x unit", () => {
    const { layout } = buildCurveFigure({ ...base, selected: new Set(["w1"]), showReported: true });
    const shapes = layout.shapes as { x0: number; line: { color: string } }[];
    expect(shapes.map((s) => s.x0)).toEqual([21.5, 22.5]);
    expect(shapes[0].line.color).toBe(dark.reference);
  });

  it("draws no lines when the switch is off", () => {
    const { layout } = buildCurveFigure({ ...base, selected: new Set(["w1"]) });
    expect(layout.shapes).toEqual([]);
  });

  it("titles the axes from the channel", () => {
    const { layout } = buildCurveFigure(base) as unknown as {
      layout: { xaxis: { title: { text: string } }; yaxis: { title: { text: string } } };
    };
    expect(layout.xaxis.title.text).toBe("°C");
    expect(layout.yaxis.title.text).toBe("Signal A (u)");
  });

  it("titles the y axis as a derivative in the derivative view", () => {
    const { layout } = buildCurveFigure({
      ...base,
      data: { ...curves, view: "derivative", window: 1.5 },
    }) as unknown as { layout: { yaxis: { title: { text: string } } } };
    expect(layout.yaxis.title.text).toBe("d(Signal A)/d(°C)");
  });

  it("uses the white canvas and the light colours for export", () => {
    const { data, layout } = buildCurveFigure({ ...base, canvas: "export" }) as unknown as {
      data: Trace[];
      layout: Record<string, unknown>;
    };
    expect(layout.paper_bgcolor).toBe(CHART_CANVAS.background);
    expect(data[0].line.color).toBe(light.reference);
  });

  it("keeps uirevision constant so a redraw keeps the zoom", () => {
    const a = buildCurveFigure(base).layout.uirevision;
    const b = buildCurveFigure({ ...base, focusedId: "w1", selected: new Set(["w1"]) }).layout
      .uirevision;
    expect(a).toBe(b);
  });
});

describe("focusIdFromHover", () => {
  it("reads the position id from the hovered trace", () => {
    expect(focusIdFromHover({ points: [{ data: { meta: "w3" } }] })).toBe("w3");
    expect(focusIdFromHover({})).toBeNull();
  });
});

describe("table helpers", () => {
  it("builds one table column per distinct reported value", () => {
    expect(reportedColumns(curves)).toEqual([
      { key: "k1:1", label: "Point 1", unit: "°C" },
      { key: "k1:2", label: "Point 2", unit: "°C" },
      { key: "k2:1", label: "Share", unit: "%" },
    ]);
  });

  it("lists the selected positions in holder order with their reported values", () => {
    const rows = tableRows(curves, new Set(["w3", "w2"]));
    expect(rows.map((r) => r.wellId)).toEqual(["w2", "w3"]);
    expect(rows[0]).toMatchObject({
      positionLabel: "Position 2",
      compound: "ABC-0000001",
      batch: "B-001",
      dose: 50,
      role: "Sample",
      note: null,
      reported: { "k1:1": 20.7 },
    });
    expect(rows[1].note).toBe("bubble");
  });
});
