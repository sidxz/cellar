import { type PanelConfig, patchPanel } from "../store/workbench-store";
import type { Dataset, DatasetColumn, Level } from "../types";
import { defaultPanels, retypePanel } from "./default-panels";
import type { Filter } from "./filters";
import { LEVELS } from "./levels";

/** What a view change takes along: the chemist's plots and filters, the selected row ids
 * (kept only at the same level, where rows keep their ids) and the old view's columns, to
 * name what the new one lacks. */
export type Carry = {
  panels: PanelConfig[];
  filters: Filter[];
  selectedIds: string[];
  columns: DatasetColumn[];
};

/** How a note names a plot type: "Plot 1: Scatter (now a histogram)". */
const TYPE_NAMES: Record<PanelConfig["type"], string> = {
  scatter: "scatter",
  histogram: "histogram",
  bar: "bar chart",
  box: "box plot",
  "rgroup-matrix": "R-group matrix",
};
const capitalized = (s: string) => s.charAt(0).toUpperCase() + s.slice(1);

/** Whether a panel still has the fields its type cannot draw without. */
function drawable(p: PanelConfig): boolean {
  switch (p.type) {
    case "scatter":
      return Boolean(p.x && p.y);
    case "histogram":
      return Boolean(p.x);
    case "box":
      return Boolean(p.y && p.category);
    case "bar":
      return Boolean(p.category && ((p.agg ?? "count") === "count" || p.y));
    case "rgroup-matrix":
      return Boolean(p.x && p.category);
  }
}

/** The plots and filters of ``prev`` fitted to the new level's dataset ``ds``: filters on
 * columns ``ds`` lacks (and any rows filter) are dropped, while substructure filters, on
 * molecule ids, always carry; panel fields on such columns are cleared, and a panel left
 * without a field its type needs becomes the level's default plot type (same id), keeping
 * the value it measured when that survives. ``dropped`` names each
 * loss for the chemist: "Filter: Well order", "Plot 1: X (Well order)", and each plot that
 * changed type, "Plot 1: Scatter (now a histogram)" — by ``labels`` when
 * it names the key, else by ``prev.columns``. */
export function carryConfig(
  prev: Carry,
  ds: Dataset,
  labels?: Record<string, string>,
): { panels: PanelConfig[]; filters: Filter[]; dropped: string[] } {
  const has = new Set(ds.columns.map((c) => c.key));
  const label = (key: string) =>
    labels?.[key] ?? prev.columns.find((c) => c.key === key)?.label ?? key;
  const dropped: string[] = [];

  const filters = prev.filters.filter((f) => {
    if (f.kind === "substructure") return true;
    if (f.kind !== "rows" && has.has(f.key)) return true;
    dropped.push(`Filter: ${f.kind === "rows" ? "Selection" : label(f.key)}`);
    return false;
  });

  const fallback = defaultPanels(ds)[0];
  const panels = prev.panels.map((p, n) => {
    const lost: string[] = [];
    /** ``key`` when the new level has it (or it is unset), else undefined, noting the loss. */
    const kept = (key: string | undefined, name: string) => {
      if (key === undefined || has.has(key)) return key;
      lost.push(`Plot ${n + 1}: ${name} (${label(key)})`);
      return undefined;
    };
    const a = p.appearance;
    const matrix = p.type === "rgroup-matrix";
    // Axes first, so the note reads in the editor's order.
    const x = kept(p.x, matrix ? "Columns" : "X");
    const y = kept(p.y, matrix ? "Value" : "Y");
    const category = kept(p.category, matrix ? "Rows" : "Group");
    const colorBy = kept(a.colorBy, "Color");
    let next: PanelConfig = {
      ...p,
      x,
      y,
      category,
      appearance: {
        ...a,
        colorBy,
        colorBins: colorBy === a.colorBy ? a.colorBins : undefined,
        shapeBy: kept(a.shapeBy, "Shape"),
        sizeBy: kept(a.sizeBy, "Size"),
        splitBy: kept(a.splitBy, "Split"),
        tooltip: a.tooltip.filter((k) => kept(k, "Tooltip") !== undefined),
      },
    };
    if (lost.length === 0) return p;
    dropped.push(...lost);
    if (!drawable(next) && fallback) {
      next = patchPanel(next, retypePanel(ds, next, fallback.type));
      // Never silently: the plot the chemist made is now another type.
      if (next.type !== p.type) {
        dropped.push(
          `Plot ${n + 1}: ${capitalized(TYPE_NAMES[p.type])} (now a ${TYPE_NAMES[next.type]})`,
        );
      }
    }
    return next;
  });

  return { panels, filters, dropped };
}

/** The note shown after a switch to ``level``; null when nothing was lost. */
export function switchNote(level: Level, dropped: string[], selected: number): string | null {
  if (dropped.length === 0 && selected === 0) return null;
  return [
    `Switched to ${LEVELS[level].label}.`,
    dropped.length > 0 && `Not available at this level: ${dropped.join(", ")}.`,
    selected > 0 && "Selection cleared — rows differ between levels.",
  ]
    .filter(Boolean)
    .join(" ");
}
