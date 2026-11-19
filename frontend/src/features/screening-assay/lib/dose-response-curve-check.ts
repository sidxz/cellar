import type { ProtocolFormValues } from "../components/create-protocol/form-values";
import type { ReadoutNormalization } from "../types";
import { WELL_CONC_X } from "./readout-constants";

type Row = ProtocolFormValues["readouts"][number];

/** The calculated layers of the numeric readout named `yName`, sorted the way the server
 *  picks its default ("none" is not a layer); empty when that readout is missing. */
export function yLayers(
  readouts: ReadonlyArray<{
    name: string;
    data_type: string;
    normalizations?: readonly string[] | null;
  }>,
  yName: string,
): ReadoutNormalization[] {
  const y = readouts.find((r) => r.name.trim() === yName.trim() && r.data_type === "numeric");
  return [...(y?.normalizations ?? [])]
    .filter((n) => n !== "none")
    .sort() as ReadoutNormalization[];
}

/** Why a dose-response row cannot fit as set up, in the scientist's words; null when it can
 *  (and for any row that is not a curve). Mirrors the server's curve check. */
export function curveProblem(row: Row, readouts: readonly Row[]): string | null {
  if (row.data_type !== "dose_response") return null;
  const y = row.dr_y_readout.trim();
  if (!y) return "Choose the readout this curve fits.";
  if (!readouts.some((r) => r !== row && r.name.trim() === y && r.data_type === "numeric")) {
    return `'${y}' is not a numeric readout of this protocol. Choose the readout this curve fits.`;
  }
  const x = row.dr_x_readout.trim();
  if (x && x !== WELL_CONC_X && !readouts.some((r) => r.name.trim() === x)) {
    return `'${x}' is not a readout of this protocol.`;
  }
  if (!fittedLayer(row, readouts) && yLayers(readouts, y).length > 1) {
    return `Choose which layer of '${y}' this curve fits.`;
  }
  return null;
}

/** The layer a curve row fits: its chosen layer while the Y readout still calculates it,
 *  else "" (the readout's only layer, or its raw values). A layer left behind by an edit to
 *  the Y readout counts as unset, so the picker (shown for 2+ layers) can always fix it. */
export function fittedLayer(row: Row, readouts: readonly Row[]): ReadoutNormalization | "" {
  const layer = row.dr_y_normalization as ReadoutNormalization | "";
  return layer && yLayers(readouts, row.dr_y_readout).includes(layer) ? layer : "";
}

export type CurveAxisRename = {
  index: number;
  field: "dr_x_readout" | "dr_y_readout";
  value: string;
};

/** The curve fields that follow the readout at `index` renamed from `oldName` to `newName`.
 *  Nothing moves when either name is empty (a cleared name is not a rename) or when another
 *  readout has the old or the new name: the name is typed one keystroke at a time, and a
 *  curve on "Signal" must not follow a new "Signal bg" while it passes through "Signal".
 *  A curve left behind is flagged by the curve check rather than moved to the wrong readout. */
export function curveAxisRenames(
  readouts: readonly Row[],
  index: number,
  oldName: string,
  newName: string,
): CurveAxisRename[] {
  const from = oldName.trim();
  const to = newName.trim();
  if (!from || !to || from === to) return [];
  const sharedName = readouts.some(
    (r, i) => i !== index && (r.name.trim() === from || r.name.trim() === to),
  );
  if (sharedName) return [];
  return readouts.flatMap((r, index) =>
    r.data_type !== "dose_response"
      ? []
      : (["dr_x_readout", "dr_y_readout"] as const)
          .filter((field) => r[field].trim() === from)
          .map((field) => ({ index, field, value: to })),
  );
}
