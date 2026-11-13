import { describe, expect, it } from "vitest";

import type { MeltWindow, MeltingStep, StepCheck } from "../types";
import type { CurvePosition } from "./curve-plot";
import {
  batchSeries,
  matchesFilter,
  maxAbsDelta,
  orderRows,
  resultRows,
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
const step = (well: string, value: number, status = "unreviewed", channel = "a") =>
  ({ well_id: well, channel_key: channel, value, status }) as unknown as MeltingStep;
const wp = (id: string, tm: number | null, d: number | null, flags: string[] = []) => ({
  well_id: id,
  tm,
  delta_tm: d,
  flags,
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
  it("status follows flags, then the counting step's review", () => {
    const w = win([
      wp("s", 60, -10, ["several_steps_in_window"]),
      wp("u", 60, -10),
      wp("a", 60, -10),
      wp("r", 60, -10),
      wp("o", 60, -10),
      wp("ref", 70, 0),
    ]);
    const positions = ["s", "u", "a", "r", "o"].map((i) => pos(i));
    positions.push(pos("ref", { well_type: "reference" }));
    const steps = [
      step("u", 60),
      step("a", 60, "accepted"),
      step("r", 60, "rejected"),
      step("r", 60, "accepted"),
      step("o", 60, "unreviewed", "b"),
      step("o", 61, "accepted"),
      step("ref", 70),
    ];
    const rows = resultRows([w], positions, steps, noChecks);
    expect(cell(rows, "s")?.status).toBe("several_steps");
    expect(cell(rows, "u")?.status).toBe("provisional");
    expect(cell(rows, "a")?.status).toBe("reviewed");
    expect(cell(rows, "r")?.status).toBe("reviewed");
    expect(cell(rows, "o")?.status).toBe("reviewed");
    expect(cell(rows, "ref")?.status).toBe("reference");
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
    const rows = resultRows([w], positions, [], noChecks);
    const { pinned, body } = orderRows(rows, ["Main"]);
    expect(pinned.map((r) => r.wellId)).toEqual(["ref"]);
    expect(body.map((r) => r.wellId)).toEqual(["big", "up", "m1", "n", "bl"]);
  });

  it("filters by needs review, provisional, up and down", () => {
    const { w, positions } = fixture();
    const rows = resultRows([w], positions, [step("up", 73)], noChecks);
    const by = (id: string) => rows.find((r) => r.wellId === id) as (typeof rows)[number];
    const m = (id: string, f: Parameters<typeof matchesFilter>[2]) =>
      matchesFilter(by(id), ["Main"], f, 2);
    expect(m("up", "up")).toBe(true);
    expect(m("big", "down")).toBe(true);
    expect(m("m1", "up") || m("m1", "down")).toBe(false);
    expect(m("up", "provisional")).toBe(true);
    expect(m("ref", "up") || m("ref", "provisional") || m("ref", "needs_review")).toBe(false);
    expect(m("bl", "down")).toBe(false);
    expect(m("m1", null)).toBe(true);
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
    const rows = resultRows([w], positions, steps, noChecks);
    const s = windowSummary(w, rows, positions, steps, noChecks, 2);
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
      resultRows([w], positions, [...steps, step("c", 70)], noChecks),
      positions,
      [...steps, step("c", 70)],
      noChecks,
      2,
    );
    expect(s2.needsReview).toBe(1);
  });

  it("counts provisional samples and references that disagree", () => {
    const w = win([wp("ref", 70, 0), wp("a", 73, 3)]);
    const positions = [pos("ref", { well_type: "reference" }), pos("a")];
    const steps = [step("ref", 70, "accepted"), step("a", 73)];
    const checks = [{ channel_key: "a", differs: ["a"], references_differ: true }] as StepCheck[];
    const rows = resultRows([w], positions, steps, checks);
    expect(rows[1].cells.Main.differs).toBe(true);
    const s = windowSummary(w, rows, positions, steps, checks, 2);
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
    const rows = resultRows([w], positions, [], noChecks);
    expect(rows.map((r) => r.cells.Main.status)).toEqual(["no_reference", "no_reference"]);
    const s = windowSummary(w, rows, positions, [], noChecks, 2);
    expect(s.up === 0 && s.down === 0).toBe(true);
    expect(s.referenceTm).toBeNull();
  });

  it("series groups by batch id and never forms a no-batch series", () => {
    const noBatch = [pos("x", { dose: 5 }), pos("y", { dose: 10 })];
    const w0 = win([wp("x", 1, -1), wp("y", 1, -2)]);
    expect(batchSeries(w0, noBatch, "any")).toEqual([]);
    const positions = [
      pos("p", { batch_id: "B", batch_number: "B-1", dose: 25 }),
      pos("q", { batch_id: "B", batch_number: "B-1", dose: 6.25 }),
      pos("z", { batch_id: "B", batch_number: "B-1", dose: 0 }),
      pos("r", { batch_id: "B", well_type: "reference", dose: 50 }),
    ];
    const w = win([wp("p", 1, -4), wp("q", 1, -2), wp("z", 1, 0), wp("r", 1, 0)]);
    expect(batchSeries(w, positions, "B")).toEqual([
      { wellId: "q", dose: 6.25, deltaTm: -2 },
      { wellId: "p", dose: 25, deltaTm: -4 },
    ]);
  });

  it("every position gets a row, even with no windows", () => {
    const positions = [pos("a"), pos("b", { well_type: "blank" }), pos("c")];
    const rows = resultRows([], positions, [], noChecks);
    expect(rows.map((r) => r.wellId)).toEqual(["a", "b", "c"]);
    expect(rows.every((r) => Object.keys(r.cells).length === 0)).toBe(true);
    expect(worstStatus(rows[0], ["Main"])).toBeNull();
    expect(maxAbsDelta(rows[0], ["Main"])).toBeNull();
    expect(matchesFilter(rows[0], ["Main"], "up", 2)).toBe(false);
    const { body } = orderRows(rows, ["Main"]);
    expect(body.map((r) => r.wellId)).toEqual(["a", "c", "b"]);
  });

  it("shiftRows excludes references, non-samples and missing values, ascending", () => {
    const { w, positions } = fixture();
    const rows = resultRows([w], positions, [], noChecks);
    expect(shiftRows(rows, "Main").map((r) => r.wellId)).toEqual(["big", "m1", "up"]);
  });

  it("duplicate labels get the position appended", () => {
    const w = win([wp("a", 1, 1), wp("b", 1, 2), wp("c", 1, 3)]);
    const positions = [
      pos("a", { label: "16:0-CoA", position_label: "Capillary 2" }),
      pos("b", { label: "16:0-CoA", position_label: "Capillary 3" }),
      pos("c", { label: "Unique" }),
    ];
    const rows = resultRows([w], positions, [], noChecks);
    expect(shiftRows(rows, "Main").map((r) => r.label)).toEqual([
      "16:0-CoA · Capillary 2",
      "16:0-CoA · Capillary 3",
      "Unique",
    ]);
  });
});
