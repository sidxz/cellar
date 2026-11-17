import { cellKey } from "@/features/sar-analysis/components/rgroup-matrix-grid";
import type { PanelConfig } from "../../store/workbench-store";
import type { Dataset } from "../../types";
import { numberAt } from "../dataset";
import { MATRIX_AXIS_CAP } from "../limits";
import { mean, median } from "./bar";
import { isCensored } from "./common";

export interface MatrixCell {
  rows: number[];
  /** Distinct compounds: the wells of one compound count once. */
  compounds: number;
  value: number | null;
}

export interface RGroupMatrix {
  /** Fragment SMILES, most-populated first, at most MATRIX_AXIS_CAP each. */
  yValues: string[];
  xValues: string[];
  yTotal: number;
  xTotal: number;
  truncated: boolean;
  /** By cellKey(y, x). */
  cells: Map<string, MatrixCell>;
  /** Passing rows without both R groups (not matching the core, or without a compound). */
  skipped: number;
  /** Of ``skipped``, the rows without a compound (controls, blanks). */
  noCompound: number;
  /** Censored values left out of the cell values. */
  censored: number;
}

const collator = new Intl.Collator(undefined, { numeric: true });

/** Axis values by distinct compounds, most first (ties in natural order), capped. */
function axis(compounds: Map<string, Set<unknown>>) {
  const size = (v: string) => compounds.get(v)?.size ?? 0;
  const all = [...compounds.keys()].sort((a, b) => size(b) - size(a) || collator.compare(a, b));
  return { values: all.slice(0, MATRIX_AXIS_CAP), total: all.length };
}

const add = (m: Map<string, Set<unknown>>, key: string, id: unknown) => {
  const s = m.get(key);
  if (s) s.add(id);
  else m.set(key, new Set([id]));
};

/** The passing rows grouped by their row R group (``cfg.category``) × column R group
 * (``cfg.x``), read from the raw fragments: each cell's rows, compounds and the median (or
 * mean) of ``cfg.y`` — censored values left out. */
export function buildRGroupMatrix(ds: Dataset, cfg: PanelConfig, mask: Uint8Array): RGroupMatrix {
  const ys = (cfg.category && ds.values[`${cfg.category}:smiles`]) || [];
  const xs = (cfg.x && ds.values[`${cfg.x}:smiles`]) || [];
  const molecules = ds.values.molecule_id ?? [];
  const groups = new Map<string, { rows: number[]; ids: Set<unknown>; values: number[] }>();
  const yIds = new Map<string, Set<unknown>>();
  const xIds = new Map<string, Set<unknown>>();
  let skipped = 0;
  let noCompound = 0;
  let censored = 0;
  for (let i = 0; i < mask.length; i++) {
    if (!mask[i]) continue;
    const y = ys[i];
    const x = xs[i];
    const id = molecules[i];
    if (typeof y !== "string" || typeof x !== "string") {
      skipped++;
      if (id == null) noCompound++;
      continue;
    }
    const key = cellKey(y, x);
    let g = groups.get(key);
    if (!g) {
      g = { rows: [], ids: new Set(), values: [] };
      groups.set(key, g);
    }
    g.rows.push(i);
    g.ids.add(id);
    add(yIds, y, id);
    add(xIds, x, id);
    const v = cfg.y ? numberAt(ds, cfg.y, i) : null;
    if (v === null) continue;
    if (isCensored(ds, cfg.y as string, i)) censored++;
    else g.values.push(v);
  }

  const agg = cfg.agg === "mean" ? mean : median;
  const cells = new Map<string, MatrixCell>();
  for (const [key, g] of groups) {
    cells.set(key, {
      rows: g.rows,
      compounds: g.ids.size,
      value: g.values.length ? agg(g.values) : null,
    });
  }
  const yAxis = axis(yIds);
  const xAxis = axis(xIds);
  return {
    yValues: yAxis.values,
    xValues: xAxis.values,
    yTotal: yAxis.total,
    xTotal: xAxis.total,
    truncated: yAxis.total > yAxis.values.length || xAxis.total > xAxis.values.length,
    cells,
    skipped,
    noCompound,
    censored,
  };
}

/** The cells holding a selected row: cheap beside the matrix, so a selection rebuilds only this. */
export function selectedCells(
  m: RGroupMatrix,
  ds: Dataset,
  selection: ReadonlySet<string>,
): Set<string> {
  const out = new Set<string>();
  if (selection.size === 0) return out;
  for (const [key, c] of m.cells) {
    if (c.rows.some((i) => selection.has(ds.row_ids[i]))) out.add(key);
  }
  return out;
}
