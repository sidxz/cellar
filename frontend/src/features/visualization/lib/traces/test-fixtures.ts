import type { DoseResponseCurve } from "@/features/screening-assay/types";
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

/** A curve with exactly the fields GET /protocols/{id}/compounds/{molecule_id}/dose-response
 * sends (the dose unit is the protocol's, spelled as stored). */
export const compoundCurve = (patch: Partial<DoseResponseCurve> = {}): DoseResponseCurve => ({
  id: "c1",
  workspace_id: "ws",
  molecule_id: "m1",
  molecule_name: null,
  batch_id: "b1",
  batch_number: null,
  protocol_id: "p1",
  run_id: "r1",
  readout_definition_id: "rd",
  curve_type: "ic50",
  fitted_value: 1,
  fitted_unit: "uM",
  hill_slope: 1,
  top: 100,
  bottom: 0,
  r_squared: 0.99,
  confidence_interval_low: null,
  confidence_interval_high: null,
  num_points: 8,
  curve_class: "active",
  raw_data: [],
  excluded_points: [],
  ...patch,
});
