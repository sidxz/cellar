import { shortId } from "@/shared/lib/utils";
import { describe, expect, it } from "vitest";

import { CHART_CANVAS, MEASURED_CURVE_COLORS } from "@/shared/lib/chart-colors";
import type { CurvePositions, RunCurves } from "../types";
import {
  type CurveSet,
  buildCurveFigure,
  colourGroupKey,
  colourGroupLabel,
  curveSetFromPositions,
  curveSetFromRun,
  focusIdFromHover,
  orderedPositions,
  positionsNotShown,
  reportedColumns,
  runHeading,
  sameDateTags,
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

  it("colours each position by its group's slot in group mode and names the legend by group", () => {
    const groups = new Map([
      ["w1", { key: "g1", label: "Group one" }],
      ["w2", { key: "g2", label: "Group two" }],
      ["w3", { key: "g1", label: "Group one" }],
    ]);
    const args = {
      ...base,
      drawn: new Set(["w1", "w2", "w3"]),
      colourMode: "group" as const,
      slots: new Map([
        ["g1", 3],
        ["g2", 0],
      ]),
      groups,
    };
    const { data } = buildCurveFigure(args) as unknown as { data: Trace[] };
    expect(data.map((t) => t.line.color)).toEqual([dark.series[3], dark.series[0], dark.series[3]]);
    const exported = buildCurveFigure({ ...args, canvas: "export" });
    expect(exported.layout.showlegend).toBe(true);
    const inLegend = exported.data.filter((t) => t.showlegend !== false).map((t) => t.name);
    expect(inLegend).toEqual(["Group one", "Group two"]);
    // The hover still names the position.
    expect(String(exported.data[0].hovertemplate)).toContain("Position 1 · Protein alone");
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

describe("colour groups", () => {
  const p = {
    ...position("w9", 1, "positive_control", null),
    molecule_id: "m1",
    molecule_name: "ABC-0000009",
    batch_id: "b1",
    batch_number: "ABC-0000009-01",
  };
  const bare = position("w8", 2, "sample", null);

  it("keys a position by its run, compound, batch or role", () => {
    expect(colourGroupKey(p, "r1", "run")).toBe("r1");
    expect(colourGroupKey(p, "r1", "compound")).toBe("m1");
    expect(colourGroupKey(p, "r1", "batch")).toBe("b1");
    expect(colourGroupKey(p, "r1", "role")).toBe("positive_control");
    expect(colourGroupKey(bare, "r1", "compound")).toBe("none");
    expect(colourGroupKey(bare, "r1", "batch")).toBe("none");
  });

  it("labels a group by the run heading, compound, batch or role", () => {
    expect(colourGroupLabel(p, "2026-11-03 · A. Person · Completed", "run")).toBe(
      "2026-11-03 · A. Person · Completed",
    );
    expect(colourGroupLabel(p, null, "compound")).toBe("ABC-0000009");
    expect(colourGroupLabel(p, null, "batch")).toBe("ABC-0000009-01");
    expect(colourGroupLabel(p, null, "role")).toBe("Positive Control");
    expect(colourGroupLabel(bare, null, "compound")).toBe("No compound");
    expect(colourGroupLabel(bare, null, "batch")).toBe("No batch");
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
    const tags = sameDateTags([
      runA,
      runB,
      runC,
      { ...runA, runId: "0a1b2c3d-0000-4000-8000-00000000000d", notes: null },
    ]);
    expect(tags.get(runA.runId)).toBe(runA.notes.slice(0, 40));
    expect(tags.get(runB.runId)).toBe("first try");
    expect(tags.get("0a1b2c3d-0000-4000-8000-00000000000d")).toMatch(/^Run [0-9a-f]+$/);
    // Alone on its date: no tag.
    expect(tags.has(runC.runId)).toBe(false);
    expect(runHeading(runA, { scientist: "A. Person", tag: undefined })).toBe(
      "2026-11-03 · A. Person · Completed",
    );
    expect(runHeading(runA, { scientist: "A. Person", tag: tags.get(runA.runId) })).toBe(
      `2026-11-03 · A. Person · Completed · ${runA.notes.slice(0, 40)}`,
    );
  });

  it("falls back to the short id when two runs on one date share the start of their notes", () => {
    const twin = {
      ...runA,
      runId: "0a1b2c3d-0000-4000-8000-000000000009",
      notes: `${runA.notes} (b)`,
    };
    const tags = sameDateTags([runA, twin, runB]);
    expect(tags.get(runA.runId)).toBe(`Run ${shortId(runA.runId)}`);
    expect(tags.get(twin.runId)).toBe(`Run ${shortId(twin.runId)}`);
    expect(tags.get(runB.runId)).toBe("first try");
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

describe("curveSetFromPositions", () => {
  const holder = { kind: "cassette", rows: 1, columns: 2, label: "Holder of 2" };
  const channel = (key: string) => ({
    key,
    label: `Signal ${key.toUpperCase()}`,
    x_unit: "°C",
    y_unit: null,
    x_label: null,
  });
  const run = (runId: string, status: string, channels: string[]) => ({
    run_id: runId,
    run_date: "2026-11-03",
    operator: "u1",
    status,
    notes: null,
    holder,
    channels: channels.map(channel),
    position_count: 2,
  });
  const at = (runId: string, column: number) => ({
    ...position(`${runId}-${column}`, column, "sample", null),
    run_id: runId,
  });
  const found: CurvePositions = {
    protocol_id: "p1",
    dose_unit: "uM",
    runs: [
      run("r2", "completed", ["b", "a"]),
      run("r1", "approved", ["a", "c"]),
      run("r3", "draft", ["a"]),
    ],
    // r3 has no position; r1's positions come out of holder order.
    positions: [at("r1", 2), at("r1", 1), at("r2", 1)],
  };
  const args = {
    channel: undefined,
    view: "measured" as const,
    window: null,
    curves: new Map(),
  };

  it("builds one group per run in the API's order, with the union of their signals", () => {
    const set = curveSetFromPositions(found, args);
    expect(set.groups.map((g) => g.key)).toEqual(["r2", "r1"]);
    expect(set.groups[1].positions.map((p) => p.well_id)).toEqual(["r1-1", "r1-2"]);
    expect(set.groups[0].run).toEqual({
      runId: "r2",
      runDate: "2026-11-03",
      operator: "u1",
      status: "completed",
      notes: null,
    });
    expect(set.groups[0].holder).toEqual(holder);
    expect(set.channels.map((c) => c.key)).toEqual(["b", "a", "c"]);
    expect(set.channel).toBe("b");
    expect(set.doseUnit).toBe("uM");
    expect(curveSetFromPositions(found, { ...args, channel: "c" }).channel).toBe("c");
  });

  it("leaves out runs whose status is hidden, and has no group when all are", () => {
    const set = curveSetFromPositions(found, { ...args, hideStatuses: ["completed"] });
    expect(set.groups.map((g) => g.key)).toEqual(["r1"]);
    expect(set.channels.map((c) => c.key)).toEqual(["a", "c"]);
    const onlyRejected: CurvePositions = {
      ...found,
      runs: [run("r1", "rejected", ["a"])],
      positions: [at("r1", 1)],
    };
    expect(
      curveSetFromPositions(onlyRejected, { ...args, hideStatuses: ["rejected"] }).groups,
    ).toEqual([]);
  });
});
