import { describe, expect, it } from "vitest";

import type { MeltWindow, MeltingStep, StepCheck } from "../types";
import type { CurvePosition } from "./curve-plot";
import {
  batchDoseCount,
  batchSeries,
  batchSuffix,
  formatDelta,
  formatTm,
  matchesFilter,
  maxAbsDelta,
  orderRows,
  resultRows,
  seriesCaption,
  seriesGaps,
  shiftRows,
  windowSummary,
  worstStatus,
} from "./melt-results";

function pos(id: string, over: Record<string, unknown> = {}) {
  return {
    well_id: id,
    position_label: id,
    label: null,
    well_type: "sample",
    registration_number: "",
    batch_id: null,
    batch_number: null,
    dose: null,
    ...over,
  } as unknown as CurvePosition;
}
/** A peak; its id is its position's unless one is given. */
const step = (well: string, value: number, status = "unreviewed", channel = "a", id = well) =>
  ({ id, well_id: well, channel_key: channel, value, status }) as unknown as MeltingStep;
type Named = Pick<MeltWindow["positions"][number], "named_by" | "step_id">;
/** A position's result. With a Tm the server names the peak that gave it: by
 *  range, the peak with the position's id, unless `over` says otherwise. */
const wp = (
  id: string,
  tm: number | null,
  d: number | null,
  flags: string[] = [],
  over: Partial<Named> = {},
) => ({
  well_id: id,
  tm,
  delta_tm: d,
  flags,
  named_by: tm == null ? null : ("range" as const),
  step_id: tm == null ? null : id,
  ...over,
});
function win(positions: MeltWindow["positions"], over: Partial<MeltWindow> = {}): MeltWindow {
  return {
    window: "Main",
    channel_key: "a",
    low: 50,
    high: 85,
    reference_tm: 70,
    reference_count: 1,
    flags: [],
    positions,
    ...over,
  } as unknown as MeltWindow;
}
const noChecks: StepCheck[] = [];
const cell = (rows: ReturnType<typeof resultRows>, id: string) =>
  rows.find((r) => r.wellId === id)?.cells.Main;

describe("melt-results", () => {
  it("status follows flags, then the review of the peak the server names", () => {
    const w = win([
      wp("s", null, null, ["several_steps_in_window"]),
      wp("u", 60, -10),
      wp("a", 60, -10),
      wp("r", 60, -10, [], { step_id: "r2" }),
      wp("o", 61, -9, [], { step_id: "o2" }),
      wp("ref", 70, 0),
    ]);
    const positions = ["s", "u", "a", "r", "o"].map((i) => pos(i));
    positions.push(pos("ref", { well_type: "reference" }));
    const steps = [
      step("u", 60),
      step("a", 60, "accepted"),
      step("r", 60, "rejected", "a", "r1"),
      step("r", 60, "accepted", "a", "r2"),
      step("o", 60, "unreviewed", "b", "o1"),
      step("o", 61, "accepted", "a", "o2"),
      step("ref", 70),
    ];
    const rows = resultRows([w], positions, steps, noChecks, []);
    expect(cell(rows, "s")?.status).toBe("several_steps");
    expect(cell(rows, "u")?.status).toBe("provisional");
    expect(cell(rows, "a")?.status).toBe("reviewed");
    expect(cell(rows, "r")?.status).toBe("reviewed");
    expect(cell(rows, "o")?.status).toBe("reviewed");
    expect(cell(rows, "ref")?.status).toBe("reference");
    // The named peak's review, references included.
    expect(cell(rows, "ref")?.review).toBe("provisional");
    expect(cell(rows, "a")?.review).toBe("reviewed");
    expect(cell(rows, "s")?.review).toBeNull();
    expect(cell(rows, "u")).toMatchObject({ namedBy: "range", stepId: "u" });
    expect(cell(rows, "s")).toMatchObject({ namedBy: null, stepId: null });
  });

  it("an assigned peak outside the range decides the review, not the one in range", () => {
    // Main is 50–85. ref and x each have an accepted peak inside it and an
    // unreviewed one below it that was assigned to Main.
    const assigned = { named_by: "assignment" as const };
    const w = win([
      wp("ref", 41, 0, [], { ...assigned, step_id: "ref-low" }),
      wp("x", 40, -1, [], { ...assigned, step_id: "x-low" }),
      wp("y", 62, 1),
    ]);
    const positions = [
      pos("ref", { well_type: "reference" }),
      pos("x", { batch_id: "B", dose: 5 }),
      pos("y", { batch_id: "B", dose: 10 }),
    ];
    const steps = [
      step("ref", 70, "accepted", "a", "ref-main"),
      step("ref", 41, "unreviewed", "a", "ref-low"),
      step("x", 60, "accepted", "a", "x-main"),
      step("x", 40, "unreviewed", "a", "x-low"),
      step("y", 62, "accepted"),
    ];
    const rows = resultRows([w], positions, steps, noChecks, []);
    expect(cell(rows, "x")).toMatchObject({
      tm: 40,
      status: "provisional",
      review: "provisional",
      namedBy: "assignment",
      stepId: "x-low",
    });
    expect(cell(rows, "ref")?.review).toBe("provisional");
    expect(windowSummary(w, rows, positions, noChecks, new Set()).referenceUnreviewed).toBe(true);
    expect(batchSeries(w, positions, "B", steps)).toEqual([
      { wellId: "x", dose: 5, deltaTm: -1, provisional: true },
      { wellId: "y", dose: 10, deltaTm: 1, provisional: false },
    ]);
  });

  it("a cell lists its position's counted peaks outside every window on the signal", () => {
    const w = win([wp("n", null, null, ["no_step_in_window"]), wp("a", 60, -10)]);
    const steps = [
      step("n", 91.5, "unreviewed", "a", "n-high"),
      step("n", 44.2, "accepted", "a", "n-low"),
      step("n", 30, "unreviewed", "b", "n-other-signal"),
      step("a", 60, "accepted"),
    ];
    const outside = ["n-high", "n-low", "n-other-signal"];
    const rows = resultRows([w], [pos("n"), pos("a")], steps, noChecks, outside);
    expect(cell(rows, "n")?.outsidePeaks).toEqual([44.2, 91.5]);
    expect(cell(rows, "a")?.outsidePeaks).toEqual([]);
  });

  it("up and down count hits only, by the sign of their ΔTm", () => {
    const w = win([wp("ref", 70, 0), wp("a", 72, 1.96), wp("b", 60, -10), wp("c", 69, -1)]);
    const positions = [pos("ref", { well_type: "reference" }), pos("a"), pos("b"), pos("c")];
    const rows = resultRows([w], positions, [], noChecks, []);
    const hits = new Set(["a", "b"]);
    const by = (id: string) => rows.find((r) => r.wellId === id) as (typeof rows)[number];
    expect(matchesFilter(by("a"), ["Main"], "up", hits)).toBe(true);
    expect(matchesFilter(by("c"), ["Main"], "down", hits)).toBe(false);
    expect(matchesFilter(by("b"), ["Main"], "hits", hits)).toBe(true);
    expect(matchesFilter(by("c"), ["Main"], "hits", hits)).toBe(false);
    expect(windowSummary(w, rows, positions, noChecks, hits)).toMatchObject({
      hits: 2,
      up: 1,
      down: 1,
    });
  });

  it("one batch-suffix rule: the registration prefix dropped, else the batch number", () => {
    expect(batchSuffix(pos("a", { registration_number: "CC-1", batch_number: "CC-1-001" }))).toBe(
      "001",
    );
    expect(batchSuffix(pos("a", { registration_number: "CC-1", batch_number: "B7" }))).toBe("B7");
    expect(batchSuffix(pos("a", { registration_number: null, batch_number: "B7" }))).toBe("B7");
    expect(batchSuffix(pos("a"))).toBeNull();
  });

  it("sample text prefers the registration number", () => {
    const rows = resultRows(
      [win([wp("a", 1, 1), wp("b", 1, 1), wp("c", 1, 1)])],
      [
        pos("a", { registration_number: "CC-014538", batch_number: "CC-014538-001" }),
        pos("b", { label: "DMSO mix" }),
        pos("c", { position_label: "Capillary 3" }),
      ],
      [],
      noChecks,
      [],
    );
    expect(rows[0].sampleText).toBe("CC-014538");
    expect(rows[0].identity.batchSuffix).toBe("001");
    expect(rows[1].sampleText).toBe("DMSO mix");
    expect(rows[2].sampleText).toBe("Capillary 3");
  });

  const fixture = () => {
    const w = win([
      wp("ref", 70, 0),
      wp("bl", 70, -5),
      wp("n", 70, null),
      wp("m1", 62, -1),
      wp("big", 61.5, -8.5),
      wp("up", 73, 3),
    ]);
    const positions = [
      pos("ref", { well_type: "reference" }),
      pos("bl", { well_type: "blank" }),
      pos("n"),
      pos("m1"),
      pos("big"),
      pos("up"),
    ];
    return { w, positions };
  };

  it("orders references, then samples by largest shift, then controls and blanks", () => {
    const { w, positions } = fixture();
    const rows = resultRows([w], positions, [], noChecks, []);
    const { pinned, body } = orderRows(rows, ["Main"]);
    expect(pinned.map((r) => r.wellId)).toEqual(["ref"]);
    expect(body.map((r) => r.wellId)).toEqual(["big", "up", "m1", "n", "bl"]);
  });

  it("filters by needs review, provisional, up and down", () => {
    const { w, positions } = fixture();
    const rows = resultRows([w], positions, [step("up", 73)], noChecks, []);
    const by = (id: string) => rows.find((r) => r.wellId === id) as (typeof rows)[number];
    const hits = new Set(["up", "big", "ref", "bl"]);
    const m = (id: string, f: Parameters<typeof matchesFilter>[2]) =>
      matchesFilter(by(id), ["Main"], f, hits);
    expect(m("up", "up")).toBe(true);
    expect(m("big", "down")).toBe(true);
    expect(m("m1", "up") || m("m1", "down")).toBe(false);
    expect(m("up", "provisional")).toBe(true);
    expect(m("ref", "up") || m("ref", "provisional") || m("ref", "needs_review")).toBe(false);
    expect(m("bl", "down")).toBe(false);
    expect(m("m1", null)).toBe(true);
    // Not evaluated: the samples the caller lists, never another role.
    const unevaluated = new Set(["n", "bl"]);
    const ne = (id: string) => matchesFilter(by(id), ["Main"], "not_evaluated", hits, unevaluated);
    expect([ne("n"), ne("m1"), ne("bl")]).toEqual([true, false, false]);
    expect(m("n", "not_evaluated")).toBe(false);
  });

  it("summary counts samples only and flags an unreviewed reference", () => {
    const w = win([
      wp("ref", 70, 0),
      wp("bl", 70, -5),
      wp("a", 73, 3),
      wp("b", 60, -10),
      wp("c", 70, null, ["no_step_in_window"]),
      wp("d", 70, 0.5),
    ]);
    const positions = [
      pos("ref", { well_type: "reference", label: "Protein" }),
      pos("bl", { well_type: "blank" }),
      ...["a", "b", "c", "d"].map((i) => pos(i)),
    ];
    const steps = [
      step("ref", 70),
      step("a", 73, "accepted"),
      step("b", 60, "accepted"),
      step("d", 70, "accepted"),
    ];
    const rows = resultRows([w], positions, steps, noChecks, []);
    const s = windowSummary(w, rows, positions, noChecks, new Set(["a", "b"]));
    expect(s).toMatchObject({
      needsReview: 1,
      provisional: 0,
      up: 1,
      down: 1,
      referenceUnreviewed: true,
      referenceCount: 1,
      referenceLabels: ["Protein"],
    });
    const s2 = windowSummary(
      w,
      resultRows([w], positions, [...steps, step("c", 70)], noChecks, []),
      positions,
      noChecks,
      new Set(),
    );
    expect(s2.needsReview).toBe(1);
  });

  it("counts provisional samples and references that disagree", () => {
    const w = win([wp("ref", 70, 0), wp("a", 73, 3)]);
    const positions = [pos("ref", { well_type: "reference" }), pos("a")];
    const steps = [step("ref", 70, "accepted"), step("a", 73)];
    const checks = [{ channel_key: "a", differs: ["a"], references_differ: true }] as StepCheck[];
    const rows = resultRows([w], positions, steps, checks, []);
    expect(rows[1].cells.Main.differs).toBe(true);
    const s = windowSummary(w, rows, positions, checks, new Set());
    expect(s.provisional).toBe(1);
    expect(s.referencesDiffer).toBe(true);
    expect(s.referenceUnreviewed).toBe(false);
  });

  it("no reference value marks rows and counts nothing", () => {
    const w = win(
      [wp("a", 60, null, ["no_reference_value"]), wp("b", 61, null, ["no_reference_value"])],
      {
        reference_tm: null,
        reference_count: 0,
      },
    );
    const positions = [pos("a"), pos("b")];
    const rows = resultRows([w], positions, [], noChecks, []);
    expect(rows.map((r) => r.cells.Main.status)).toEqual(["no_reference", "no_reference"]);
    const s = windowSummary(w, rows, positions, noChecks, new Set(["a"]));
    expect(s.up === 0 && s.down === 0).toBe(true);
    expect(s.referenceTm).toBeNull();
  });

  it("series groups by batch id and never forms a no-batch series", () => {
    const noBatch = [pos("x", { dose: 5 }), pos("y", { dose: 10 })];
    const w0 = win([wp("x", 1, -1), wp("y", 1, -2)]);
    expect(batchSeries(w0, noBatch, "any", [])).toEqual([]);
    const positions = [
      pos("p", { batch_id: "B", batch_number: "B-1", dose: 25 }),
      pos("q", { batch_id: "B", batch_number: "B-1", dose: 6.25 }),
      pos("z", { batch_id: "B", batch_number: "B-1", dose: 0 }),
      pos("r", { batch_id: "B", well_type: "reference", dose: 50 }),
    ];
    const w = win([wp("p", 1, -4), wp("q", 1, -2), wp("z", 1, 0), wp("r", 1, 0)]);
    // q's peak is unreviewed: provisional; p's is accepted.
    const steps = [step("q", 60), step("p", 60, "accepted")];
    expect(batchSeries(w, positions, "B", steps)).toEqual([
      { wellId: "q", dose: 6.25, deltaTm: -2, provisional: true },
      { wellId: "p", dose: 25, deltaTm: -4, provisional: false },
    ]);
    expect(batchDoseCount(positions, "B")).toBe(2);
    expect(
      batchDoseCount(
        [pos("x", { batch_id: "C", dose: 5 }), pos("y", { batch_id: "C", dose: 5 })],
        "C",
      ),
    ).toBe(1);
  });

  it("seriesGaps counts the batch's concentrations above zero that have no ΔTm", () => {
    const positions = [1, 2, 3, 4, 5].map((d) => pos(`d${d}`, { batch_id: "B", dose: d }));
    positions.push(
      // A second position at 3, without a ΔTm: 3 still has one.
      pos("d3b", { batch_id: "B", dose: 3 }),
      pos("zero", { batch_id: "B", dose: 0 }),
      pos("other", { batch_id: "C", dose: 9 }),
      pos("ref", { batch_id: "B", well_type: "reference", dose: 7 }),
    );
    // d5 is not in the window at all (no trace on its signal).
    const w = win([
      wp("d1", 60, -1),
      wp("d2", 60, -2),
      wp("d3", 60, -3),
      wp("d3b", null, null, ["no_step_in_window"]),
      wp("d4", null, null, ["no_step_in_window"]),
      wp("zero", 70, 0),
      wp("ref", 70, 0),
    ]);
    expect(seriesGaps(w, positions, "B")).toEqual({ missing: 2, total: 5 });
    expect(seriesGaps(w, positions, "C")).toEqual({ missing: 1, total: 1 });
    expect(seriesGaps(w, positions, "none")).toEqual({ missing: 0, total: 0 });
  });

  it("every position gets a row, even with no windows", () => {
    const positions = [pos("a"), pos("b", { well_type: "blank" }), pos("c")];
    const rows = resultRows([], positions, [], noChecks, []);
    expect(rows.map((r) => r.wellId)).toEqual(["a", "b", "c"]);
    expect(rows.every((r) => Object.keys(r.cells).length === 0)).toBe(true);
    expect(worstStatus(rows[0], ["Main"])).toBeNull();
    expect(maxAbsDelta(rows[0], ["Main"])).toBeNull();
    expect(matchesFilter(rows[0], ["Main"], "up", new Set(["a"]))).toBe(false);
    const { body } = orderRows(rows, ["Main"]);
    expect(body.map((r) => r.wellId)).toEqual(["a", "c", "b"]);
  });

  it("shiftRows excludes references, non-samples and missing values, ascending", () => {
    const { w, positions } = fixture();
    const rows = resultRows([w], positions, [], noChecks, []);
    expect(shiftRows(rows, "Main").map((r) => r.wellId)).toEqual(["big", "m1", "up"]);
  });

  it("duplicate labels get the position appended", () => {
    const w = win([wp("a", 1, 1), wp("b", 1, 2), wp("c", 1, 3)]);
    const positions = [
      pos("a", { label: "16:0-CoA", position_label: "Capillary 2" }),
      pos("b", { label: "16:0-CoA", position_label: "Capillary 3" }),
      pos("c", { label: "Unique" }),
    ];
    const rows = resultRows([w], positions, [], noChecks, []);
    expect(shiftRows(rows, "Main").map((r) => r.label)).toEqual([
      "16:0-CoA · Capillary 2",
      "16:0-CoA · Capillary 3",
      "Unique",
    ]);
  });
});

describe("seriesCaption", () => {
  const series = (measure: string, values: unknown[], extra: Record<string, unknown> = {}) => ({
    readout_id: measure,
    readout_name: measure,
    measure,
    threshold: null,
    concentration: null,
    values,
    ...extra,
  });
  const v = (batch_id: string, value: number, concentration: number | null, qualifier = "=") => ({
    batch_id,
    value,
    qualifier,
    concentration,
  });
  const w = (s: unknown[]) => win([], { series: s } as Partial<MeltWindow>);

  it("names the batch's stored values, in the window's order", () => {
    const window = w([
      series("max_delta_tm", [v("b1", -8.64, 25), v("b2", 1, 10)]),
      series("lowest_shift_concentration", [v("b1", 6.25, 6.25)], { threshold: 2 }),
      series("delta_tm_at_concentration", [v("b1", -8.1, 50)], { concentration: 50 }),
    ]);
    expect(seriesCaption(window, "b1", "µM")).toBe(
      "Max ΔTm −8.6 °C at 25 µM · Lowest shifting conc. 6.25 µM · ΔTm at 50 µM −8.1 °C",
    );
  });

  it("says a censored lowest concentration was not reached, and skips what the batch lacks", () => {
    const window = w([
      series("max_delta_tm", [v("b1", 1.2, null)]),
      series("lowest_shift_concentration", [v("b1", 50, 50, ">")], { threshold: 2 }),
      series("delta_tm_at_concentration", [], { concentration: 100 }),
    ]);
    expect(seriesCaption(window, "b1", "µM")).toBe(
      "Max ΔTm +1.2 °C · Lowest shifting conc. > 50 µM",
    );
    expect(seriesCaption(window, "other", "µM")).toBe("");
  });
});

describe("formatDelta and formatTm", () => {
  it("show one decimal, a ΔTm with its sign", () => {
    expect(formatDelta(1.44)).toBe("+1.4");
    expect(formatDelta(-8.5)).toBe("−8.5");
    expect(formatDelta(0.04)).toBe("0.0");
    expect(formatDelta(-0.04)).toBe("0.0");
    expect(formatDelta(-2.02)).toBe("−2.0");
    expect(formatDelta(-2.02, [])).toBe("−2.0");
    expect(formatTm(57.98)).toBe("58.0");
  });

  it("show two decimals where one would read as a limit the value is not on", () => {
    const limits = [-2, 2];
    expect(formatDelta(-2.02, limits)).toBe("−2.02");
    expect(formatDelta(-1.96, limits)).toBe("−1.96");
    expect(formatDelta(2.03, limits)).toBe("+2.03");
    // On the limit, or clear of it at one decimal, nothing is hidden.
    expect(formatDelta(-2, limits)).toBe("−2.0");
    expect(formatDelta(-2.4, limits)).toBe("−2.4");
    expect(formatDelta(1.44, limits)).toBe("+1.4");
    expect(formatTm(59.96, [60])).toBe("59.96");
    expect(formatTm(60, [60])).toBe("60.0");
    expect(formatTm(61.2, [60])).toBe("61.2");
  });
});
