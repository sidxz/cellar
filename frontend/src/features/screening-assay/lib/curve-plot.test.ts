import { describe, expect, it } from "vitest";

import { CHART_CANVAS, MEASURED_CURVE_COLORS } from "@/shared/lib/chart-colors";
import type { RunCurves } from "../types";
import {
  type CurveSet,
  buildCurveFigure,
  curveSetFromRun,
  focusIdFromHover,
  orderedPositions,
  positionsNotShown,
  reportedColumns,
  runHeading,
  runsSharingADate,
  tableRows,
} from "./curve-plot";

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
    registration_number: id === "w2" ? "REG-0001" : null,
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
  channels: [{ key: "a", label: "Signal A", x_unit: "°C", y_unit: "u", x_label: null }],
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
  set: curveSetFromRun(curves),
  drawn: new Set(["w1", "w3"]),
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
    const { layout } = buildCurveFigure({ ...base, drawn: new Set(["w1"]), showReported: true });
    const shapes = layout.shapes as { x0: number; line: { color: string } }[];
    expect(shapes.map((s) => s.x0)).toEqual([21.5, 22.5]);
    expect(shapes[0].line.color).toBe(dark.reference);
  });

  it("draws no lines when the switch is off", () => {
    const { layout } = buildCurveFigure({ ...base, drawn: new Set(["w1"]) });
    expect(layout.shapes).toEqual([]);
  });

  it("titles the axes from the channel", () => {
    const { layout } = buildCurveFigure(base) as unknown as {
      layout: { xaxis: { title: { text: string } }; yaxis: { title: { text: string } } };
    };
    expect(layout.xaxis.title.text).toBe("°C");
    expect(layout.yaxis.title.text).toBe("Signal A (u)");
  });

  it("names the x axis with its quantity when the API gives one", () => {
    const named = {
      ...curves,
      channels: [{ ...curves.channels[0], x_label: "Temperature" }],
    };
    const { layout } = buildCurveFigure({ ...base, set: curveSetFromRun(named) }) as unknown as {
      layout: { xaxis: { title: { text: string } } };
    };
    expect(layout.xaxis.title.text).toBe("Temperature [°C]");
    const derivative = buildCurveFigure({
      ...base,
      set: curveSetFromRun({ ...named, view: "derivative", window: 1.5 }),
    }) as unknown as { layout: { yaxis: { title: { text: string } } } };
    expect(derivative.layout.yaxis.title.text).toBe("d(Signal A)/d(°C)");
  });

  it("titles the y axis as a derivative in the derivative view", () => {
    const { layout } = buildCurveFigure({
      ...base,
      set: curveSetFromRun({ ...curves, view: "derivative", window: 1.5 }),
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

  it("puts a legend on the exported figure in Distinct mode only", () => {
    const legend = (colourMode: "highlight" | "distinct") =>
      buildCurveFigure({ ...base, canvas: "export", colourMode }).layout.showlegend;
    expect(legend("distinct")).toBe(true);
    expect(legend("highlight")).toBe(false);
    expect(buildCurveFigure({ ...base, colourMode: "distinct" }).layout.showlegend).toBe(false);
  });

  it("keeps uirevision constant so a redraw keeps the zoom", () => {
    const a = buildCurveFigure(base).layout.uirevision;
    const b = buildCurveFigure({ ...base, focusedId: "w1", drawn: new Set(["w1"]) }).layout
      .uirevision;
    expect(a).toBe(b);
  });
});

describe("curve sets", () => {
  it("turns a run's curves into a set with one group and a curve per position", () => {
    const set = curveSetFromRun(curves);
    expect(set.groups).toHaveLength(1);
    expect(set.groups[0].run).toBeNull();
    expect(set.curves.get("w1")?.x).toEqual(curves.curves[0].x);
  });

  it("draws positions of two groups in group order", () => {
    const one = curveSetFromRun(curves);
    const run = (runId: string) => ({
      runId,
      runDate: "2026-11-03",
      operator: "u1",
      status: "completed",
      notes: null,
    });
    const other = curves.positions.map((p) => ({ ...p, well_id: `x${p.column}` }));
    const set: CurveSet = {
      ...one,
      groups: [
        { key: "r2", run: run("r2"), holder: curves.holder, positions: other },
        { ...one.groups[0], run: run("r1") },
      ],
      curves: new Map([
        ...one.curves,
        ...curves.curves.map((c) => [`x${c.well_id.slice(1)}`, c] as const),
      ]),
    };
    expect(orderedPositions(set).map((p) => p.well_id)).toEqual([
      "x1",
      "x2",
      "x3",
      "w1",
      "w2",
      "w3",
    ]);
    const { data } = buildCurveFigure({ ...base, set, drawn: new Set(["w1", "x3"]) });
    expect(data.map((t) => t.meta)).toEqual(["x3", "w1"]);
    expect(tableRows(set, new Set(["w2", "x1"])).map((r) => r.wellId)).toEqual(["x1", "w2"]);
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
    expect(reportedColumns(curveSetFromRun(curves))).toEqual([
      { key: "k1:1", label: "Point 1", unit: "°C" },
      { key: "k1:2", label: "Point 2", unit: "°C" },
      { key: "k2:1", label: "Share", unit: "%" },
    ]);
  });

  it("lists the selected positions in holder order with their reported values", () => {
    const rows = tableRows(curveSetFromRun(curves), new Set(["w3", "w2"]));
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

describe("run groups", () => {
  const runA = {
    runId: "0a1b2c3d-0000-4000-8000-000000000001",
    runDate: "2026-11-03",
    operator: "u1",
    status: "completed",
    notes: "second attempt, new buffer, longer equilibration before the ramp",
  };
  const runB = { ...runA, runId: "0a1b2c3d-0000-4000-8000-000000000002", notes: "first try" };
  const runC = { ...runA, runId: "0a1b2c3d-0000-4000-8000-000000000003", runDate: "2026-11-04" };

  it("tells two runs on the same date apart by the start of their notes, or by a short id without notes", () => {
    expect(runHeading(runA, { scientist: "A. Person", sameDate: false })).toBe(
      "2026-11-03 · A. Person · Completed",
    );
    expect(runHeading(runA, { scientist: "A. Person", sameDate: true })).toContain(
      "second attempt, new buffer",
    );
    expect(runHeading(runA, { scientist: "A. Person", sameDate: true })).toBe(
      `2026-11-03 · A. Person · Completed · ${runA.notes.slice(0, 40)}`,
    );
    expect(
      runHeading({ ...runA, notes: null }, { scientist: "A. Person", sameDate: true }),
    ).toMatch(/Run [0-9a-f]+$/);
    expect([...runsSharingADate([runA, runB, runC])]).toEqual([runA.runId, runB.runId]);
  });

  it("lists drawn positions that have no curve in the set", () => {
    const set = curveSetFromRun({
      ...curves,
      curves: curves.curves.filter((c) => c.well_id !== "w2"),
    });
    expect(positionsNotShown(set, ["w1", "w2", "w3"]).map((p) => p.well_id)).toEqual(["w2"]);
    expect(positionsNotShown(set, ["w1"])).toEqual([]);
  });
});
