import { describe, expect, it } from "vitest";

import type { InstrumentPreview } from "../types";
import {
  buildLabelling,
  canImportInstrumentFile,
  draftFromPreview,
  labellingSummary,
  positionKey,
  selectableReadouts,
  seriesKey,
  setRoleForPositions,
} from "./instrument-labelling";

const preview: InstrumentPreview = {
  reader: "reader-1",
  reader_label: "Reader one",
  holder: { kind: "cassette", rows: 1, columns: 3, label: "Holder of 3" },
  dose_unit: "uM",
  positions: [
    {
      row: 1,
      column: 1,
      position_label: "Position 1",
      label: "ABC-0000001",
      suggestion: {
        molecule_id: "m1",
        molecule_name: "ABC-0000001",
        batches: [{ batch_id: "b1", batch_number: "B-1" }],
        batch_id: "b1",
      },
    },
    {
      row: 1,
      column: 2,
      position_label: "Position 2",
      label: "ABC-0000002",
      suggestion: {
        molecule_id: "m2",
        molecule_name: "ABC-0000002",
        batches: [
          { batch_id: "b2", batch_number: "B-2" },
          { batch_id: "b3", batch_number: "B-3" },
          { batch_id: "b4", batch_number: "B-4" },
        ],
        batch_id: null,
      },
    },
    { row: 1, column: 3, position_label: "Position 3", label: "", suggestion: null },
  ],
  channels: [
    { key: "ratio", label: "Channel A", x_unit: "°C", y_unit: null, x_label: null },
    { key: "f330", label: "Channel B", x_unit: "°C", y_unit: null, x_label: null },
    { key: "f350", label: "Channel C", x_unit: "°C", y_unit: null, x_label: null },
    { key: "scattering", label: "Channel D", x_unit: "°C", y_unit: null, x_label: null },
  ],
  series: [
    {
      channel: "ratio",
      kind: "transition",
      ordinal: 1,
      label: "Transition 1",
      unit: "°C",
      count: 3,
      suggested_readout_definition_id: "r1",
    },
    {
      channel: "ratio",
      kind: "onset",
      ordinal: 1,
      label: "Onset 1",
      unit: "°C",
      count: 2,
      suggested_readout_definition_id: null,
    },
  ],
  readouts: [
    { id: "r1", name: "Transition 1", unit: "°C" },
    { id: "r2", name: "Percent", unit: "%" },
    { id: "r3", name: "Onset", unit: "°C" },
  ],
  settings: {},
  warnings: [],
};

const draft = draftFromPreview(preview);

function withPosition(i: number, patch: Partial<(typeof draft.positions)[number]>) {
  return { ...draft, positions: draft.positions.map((p, j) => (j === i ? { ...p, ...patch } : p)) };
}

describe("instrument labelling", () => {
  it("pre-fills from the preview and never selects a batch the API did not", () => {
    // position 1: one batch pre-selected; position 2: three batches, none; position 3: blank label, no suggestion
    expect(draft.positions.map((p) => p.batchId)).toEqual(["b1", null, null]);
    expect(draft.positions[1].batchOptions).toHaveLength(3);
    expect(draft.positions[2]).toMatchObject({ used: true, label: "", moleculeId: null });
    expect(draft.positions.every((p) => p.wellType === "sample" && p.note === "")).toBe(true);
    expect(draft.readoutBySeries[seriesKey(preview.series[0])]).toBe("r1");
    expect(draft.readoutBySeries[seriesKey(preview.series[1])]).toBeNull();
  });

  it("builds the payload with every position, used or not", () => {
    const out = buildLabelling(
      { ...draft, positions: draft.positions.map((p, i) => (i === 2 ? { ...p, used: false } : p)) },
      preview,
    );
    expect(out?.positions).toHaveLength(3);
    expect(out?.positions[2].used).toBe(false);
    expect(out?.series).toEqual([
      { channel: "ratio", kind: "transition", ordinal: 1, readout_definition_id: "r1" },
    ]);
  });

  it("carries each position's note into the payload", () => {
    const out = buildLabelling(withPosition(0, { note: "precipitate seen" }), preview);
    expect(out?.positions.map((p) => p.note)).toEqual(["precipitate seen", "", ""]);
  });

  it("turns a blank dose into null and refuses a negative or non-numeric one", () => {
    expect(buildLabelling(withPosition(0, { dose: "" }), preview)?.positions[0].dose).toBeNull();
    expect(buildLabelling(withPosition(0, { dose: "12.5" }), preview)?.positions[0].dose).toBe(
      12.5,
    );
    expect(buildLabelling(withPosition(0, { dose: "-1" }), preview)).toBeNull();
    expect(buildLabelling(withPosition(0, { dose: "abc" }), preview)).toBeNull();
  });

  it("refuses a label over 200 characters", () => {
    expect(buildLabelling(withPosition(0, { label: "x".repeat(200) }), preview)).not.toBeNull();
    expect(buildLabelling(withPosition(0, { label: "x".repeat(201) }), preview)).toBeNull();
  });

  it("refuses a note over 1000 characters", () => {
    expect(buildLabelling(withPosition(0, { note: "x".repeat(1000) }), preview)).not.toBeNull();
    expect(buildLabelling(withPosition(0, { note: "x".repeat(1001) }), preview)).toBeNull();
  });

  it("sets one role on all selected positions and leaves the rest", () => {
    const keys = new Set([positionKey(preview.positions[0]), positionKey(preview.positions[2])]);
    const out = setRoleForPositions(draft, keys, "reference");
    expect(out.positions.map((p) => p.wellType)).toEqual(["reference", "sample", "reference"]);
  });

  it("disables a readout whose unit differs or that another series uses", () => {
    const options = selectableReadouts(preview, preview.series[1], draft.readoutBySeries);
    expect(options.map((o) => [o.id, o.disabled])).toEqual([
      ["r1", true],
      ["r2", true],
      ["r3", false],
    ]);
    expect(options[0].reason).toBe("already used");
    expect(options[1].reason).toBe("different unit");
    // A series' own choice stays selectable for it.
    const own = selectableReadouts(preview, preview.series[0], draft.readoutBySeries);
    expect(own.find((o) => o.id === "r1")?.disabled).toBe(false);
  });

  it("summarises used, unused, without batch, curves and values", () => {
    expect(labellingSummary(draft, preview)).toEqual({
      used: 3,
      unused: 0,
      withoutBatch: 2,
      curves: 12,
      values: 3,
    });
  });

  it("allows import only on unlocked draft or in-progress runs", () => {
    expect(canImportInstrumentFile({ is_locked: false, status: "draft" })).toBe(true);
    expect(canImportInstrumentFile({ is_locked: false, status: "in_progress" })).toBe(true);
    expect(canImportInstrumentFile({ is_locked: false, status: "completed" })).toBe(false);
    expect(canImportInstrumentFile({ is_locked: true, status: "in_progress" })).toBe(false);
  });
});
