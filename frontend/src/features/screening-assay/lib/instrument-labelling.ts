/**
 * Pure state for the instrument file import wizard: the editable draft built
 * from the preview, and the `labelling` payload built from the draft.
 */

import type { InstrumentLabelling } from "../hooks/use-instrument-import";
import type { InstrumentPreview, Run, WellType } from "../types";

const MAX_LABEL = 200;
const MAX_NOTE = 1000;

export interface PositionDraft {
  row: number;
  column: number;
  positionLabel: string;
  used: boolean;
  label: string;
  note: string;
  wellType: WellType;
  moleculeId: string | null;
  moleculeName: string | null;
  batchId: string | null;
  /** Text while editing; parsed in {@link buildLabelling}. */
  dose: string;
}

export interface LabellingDraft {
  positions: PositionDraft[];
  readoutBySeries: Record<string, string | null>;
}

export interface ReadoutChoice {
  id: string;
  name: string;
  disabled: boolean;
  reason: "different unit" | "already used" | null;
}

export function seriesKey(s: { channel: string; kind: string; ordinal: number }): string {
  return `${s.channel}|${s.kind}|${s.ordinal}`;
}

export function positionKey(p: { row: number; column: number }): string {
  return `${p.row}:${p.column}`;
}

export function draftFromPreview(preview: InstrumentPreview): LabellingDraft {
  return {
    positions: preview.positions.map((p) => ({
      row: p.row,
      column: p.column,
      positionLabel: p.position_label,
      used: true,
      label: p.label,
      note: "",
      wellType: "sample",
      moleculeId: p.suggestion?.molecule_id ?? null,
      moleculeName: p.suggestion?.molecule_name ?? null,
      // Only what the API pre-selected; several batches means the user chooses.
      batchId: p.suggestion?.batch_id ?? null,
      dose: "",
    })),
    readoutBySeries: Object.fromEntries(
      preview.series.map((s) => [seriesKey(s), s.suggested_readout_definition_id]),
    ),
  };
}

export function setRoleForPositions(
  draft: LabellingDraft,
  keys: ReadonlySet<string>,
  wellType: WellType,
): LabellingDraft {
  return {
    ...draft,
    positions: draft.positions.map((p) => (keys.has(positionKey(p)) ? { ...p, wellType } : p)),
  };
}

/** The protocol's readouts for one reported series, with why any cannot take it. */
export function selectableReadouts(
  preview: InstrumentPreview,
  series: { channel: string; kind: string; ordinal: number; unit: string },
  readoutBySeries: Record<string, string | null>,
): ReadoutChoice[] {
  const own = seriesKey(series);
  const taken = new Set(
    Object.entries(readoutBySeries)
      .filter(([key, id]) => key !== own && id)
      .map(([, id]) => id),
  );
  return preview.readouts.map((r) => {
    const reason =
      (r.unit ?? "") !== series.unit ? "different unit" : taken.has(r.id) ? "already used" : null;
    return { id: r.id, name: r.name, disabled: reason !== null, reason };
  });
}

/** A blank dose is null; anything else must be a non-negative number. */
function parseDose(text: string): number | null | undefined {
  const t = text.trim();
  if (t === "") return null;
  const n = Number(t);
  return Number.isFinite(n) && n >= 0 ? n : undefined;
}

/** Why the draft cannot be imported yet, naming the first used position that holds an
 *  invalid value, or null when it can. */
export function labellingProblem(draft: LabellingDraft): string | null {
  for (const p of draft.positions) {
    if (!p.used) continue;
    if (parseDose(p.dose) === undefined) {
      return `${p.positionLabel}: the concentration must be a number, 0 or more.`;
    }
    if (p.label.length > MAX_LABEL) {
      return `${p.positionLabel}: the label is longer than ${MAX_LABEL} characters.`;
    }
    if (p.note.length > MAX_NOTE) {
      return `${p.positionLabel}: the note is longer than ${MAX_NOTE} characters.`;
    }
  }
  return null;
}

/** The `labelling` payload, or null while a used position holds an invalid value. */
export function buildLabelling(
  draft: LabellingDraft,
  preview: InstrumentPreview,
): InstrumentLabelling | null {
  if (labellingProblem(draft) !== null) return null;
  const positions: InstrumentLabelling["positions"] = [];
  for (const p of draft.positions) {
    const dose = parseDose(p.dose);
    positions.push({
      row: p.row,
      column: p.column,
      used: p.used,
      label: p.label,
      note: p.note,
      well_type: p.wellType,
      batch_id: p.batchId,
      dose: dose ?? null,
    });
  }
  const series = preview.series.flatMap((s) => {
    const id = draft.readoutBySeries[seriesKey(s)];
    return id
      ? [{ channel: s.channel, kind: s.kind, ordinal: s.ordinal, readout_definition_id: id }]
      : [];
  });
  return { positions, series };
}

export function labellingSummary(
  draft: LabellingDraft,
  preview: InstrumentPreview,
): { used: number; unused: number; withoutBatch: number; curves: number; values: number } {
  const used = draft.positions.filter((p) => p.used);
  // ponytail: the preview counts values per series, not per position, so with
  // unused positions this is an upper bound; per-position presence would make it exact.
  const values = preview.series
    .filter((s) => draft.readoutBySeries[seriesKey(s)])
    .reduce((sum, s) => sum + Math.min(s.count, used.length), 0);
  return {
    used: used.length,
    unused: draft.positions.length - used.length,
    withoutBatch: used.filter((p) => !p.batchId).length,
    curves: used.length * preview.channels.length,
    values,
  };
}

/** Why the run cannot take an instrument file, or null when it can. */
export function instrumentFileRefusal(run: Pick<Run, "is_locked" | "status">): string | null {
  if (run.is_locked) return "The run is locked.";
  if (run.status !== "draft" && run.status !== "in_progress") {
    return "Only draft or in-progress runs accept an instrument file.";
  }
  return null;
}

export function canImportInstrumentFile(run: Pick<Run, "is_locked" | "status">): boolean {
  return instrumentFileRefusal(run) === null;
}
