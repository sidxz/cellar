import { describe, expect, it } from "vitest";

import type { MeltWindow, StepCheck } from "../types";
import type { CurvePosition } from "./curve-plot";
import { concentrationSeries, windowRows } from "./melt-results";

function pos(id: string, wellType: string, batch: string | null, dose: number | null) {
  return {
    well_id: id,
    position: id,
    row: "A",
    column: 1,
    well_type: wellType,
    registration_number: null,
    batch_id: null,
    batch_number: batch,
    position_label: `Position ${id}`,
    label: null,
    note: null,
    dose,
  } as CurvePosition;
}

const positions = [
  pos("r", "reference", null, null),
  pos("a1", "sample", "B-1", 1),
  pos("a2", "sample", "B-1", 10),
  pos("a3", "sample", "B-1", 10),
  pos("b1", "sample", "B-2", 5),
  pos("c0", "sample", "B-3", 0),
  pos("c1", "sample", "B-3", 2),
];

function win(over: Partial<MeltWindow> = {}): MeltWindow {
  return {
    window: "Main",
    channel_key: "a",
    low: 50,
    high: 85,
    tm_readout_id: "t",
    delta_tm_readout_id: "d",
    reference_tm: 71.3,
    reference_count: 1,
    flags: [],
    positions: [
      { well_id: "r", tm: 71.3, delta_tm: null, flags: [] },
      { well_id: "a1", tm: 64, delta_tm: -7.3, flags: ["several_steps_in_window"] },
      { well_id: "a2", tm: 68, delta_tm: -3.3, flags: [] },
      { well_id: "a3", tm: 69, delta_tm: -2.3, flags: [] },
      { well_id: "b1", tm: null, delta_tm: null, flags: ["no_step_in_window"] },
      { well_id: "c0", tm: 71, delta_tm: -0.3, flags: [] },
      { well_id: "c1", tm: 72, delta_tm: 0.7, flags: [] },
    ],
    ...over,
  } as MeltWindow;
}

const checks: StepCheck[] = [{ channel_key: "a", differs: ["b1"], references_differ: false }];

describe("windowRows", () => {
  it("joins positions and writes flag text", () => {
    const rows = windowRows(win(), positions, checks);
    expect(rows).toHaveLength(7);
    expect(rows[1]).toMatchObject({
      position: "Position a1",
      role: "Sample",
      batch: "B-1",
      concentration: 1,
      tm: 64,
      deltaTm: -7.3,
      flags: "Several steps in window",
    });
    expect(rows[0]).toMatchObject({ role: "Reference", deltaTm: null });
    expect(rows[4].flags).toBe("No step in window, Step count differs from the reference");
  });
});

describe("concentrationSeries", () => {
  it("keeps batches with two or more doses and sorts by dose", () => {
    const w = win();
    w.positions = [w.positions[2], w.positions[1], ...w.positions.slice(3)];
    expect(concentrationSeries(w, positions)).toEqual([
      {
        batchLabel: "B-1",
        points: [
          { dose: 1, deltaTm: -7.3 },
          { dose: 10, deltaTm: -3.3 },
          { dose: 10, deltaTm: -2.3 },
        ],
      },
    ]);
  });
});
