import { DEFAULT_APPEARANCE, type PanelConfig, type PanelPatch } from "../../store/workbench-store";
import type { Dataset, DatasetColumn } from "../../types";

type Kind = DatasetColumn["kind"];

/** A column's provenance as the server sends it: ``rd:<readout>:<layer>`` values carry their
 * readout id, their ``:q`` / ``:outlier`` / ``:n`` … siblings also a stat. */
export function provenanceOf(key: string): DatasetColumn["provenance"] {
  if (!key.startsWith("rd:")) return {};
  const [, readout, layer, stat] = key.split(":");
  return {
    readout_definition_id: readout,
    layer,
    ...(stat && { stat: stat === "q" ? "qualifier" : stat }),
  };
}

/** A dataset from columns of values; a column is numeric when its first value is a number.
 * Column ``y`` is labeled "Signal". */
export function dataset(
  values: Record<string, unknown[]>,
  kinds: Record<string, Kind> = {},
): Dataset {
  const n = Object.values(values)[0].length;
  const kindOf = (k: string): Kind =>
    kinds[k] ?? (typeof values[k].find((v) => v != null) === "number" ? "number" : "category");
  return {
    revision: "r",
    level: "wells",
    row_count: n,
    row_ids: Array.from({ length: n }, (_, i) => `w${i}`),
    columns: Object.keys(values).map((key) => ({
      key,
      label: key === "y" ? "Signal" : key,
      kind: kindOf(key),
      provenance: provenanceOf(key),
    })),
    values,
  };
}

export const panel = (type: PanelConfig["type"], patch: PanelPatch = {}): PanelConfig => ({
  id: "p1",
  type,
  ...patch,
  appearance: { ...DEFAULT_APPEARANCE, ...patch.appearance },
});

export const pass = (n: number) => new Uint8Array(n).fill(1);

export interface Trace {
  type: string;
  name?: string;
  x: unknown[];
  y: unknown[];
  width?: number;
  boxpoints?: string;
  marker: { color?: unknown };
}
export const traces = (fig: { data: Record<string, unknown>[] }) => fig.data as unknown as Trace[];
